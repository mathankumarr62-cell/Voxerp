"""Release coverage migrated to Django; academic writes use isolated SQLite."""
import sqlite3
from unittest import mock
import pytest
import db_adapter
from api import views
from api.services import VoxERPService
from intelligence.intent_engine import IntentEngine
from intelligence.rbac import authorize_request

pytestmark = pytest.mark.django_db

@pytest.fixture
def client(client, django_user_model, monkeypatch):
    user = django_user_model.objects.create_user(username="student-1", password="test-password")
    client.force_login(user)
    monkeypatch.setenv("VOXERP_OFFLINE_MODE", "True")
    monkeypatch.setattr(views, "service", VoxERPService(IntentEngine(client=object())))
    return client

def post(client, path, payload):
    return client.post(path, data=payload, content_type="application/json")

def pending(client):
    result = post(client, "/api/query/", {"text": "Mark my DBMS attendance absent period 2"})
    assert result.status_code == 200
    return result.json()["pending"]

def test_own_reads_and_body_identity_cannot_override(client):
    for text, expected in [("Show my DBMS marks", "88"), ("Show my timetable", "Monday"), ("Show my DBMS attendance", "present")]:
        response = post(client, "/api/query/", {"text": text, "student_id": "student-2", "user_id": "student-2", "role": "teacher"})
        assert response.status_code == 200
        assert expected in response.json()["reply_text"]

def test_cross_student_denied_before_read(client):
    with mock.patch.object(db_adapter, "get_marks") as read:
        response = post(client, "/api/query/", {"text": "Show another student's marks"})
    assert "only access your own" in response.json()["reply_text"]
    read.assert_not_called()

@pytest.mark.parametrize("path", ["/.env", "/voxerp.db", "/db_adapter.py", "/app.py", "/requirements.txt", "/.git/config", "/db_adapter.py.manual-backup", "/voxerp_app.sqlite3"])
def test_private_files_not_served(client, path):
    assert client.get(path).status_code == 404
    assert client.get("/").status_code == 200

def test_signed_confirmation_reauthorization_and_idempotency(client, django_user_model):
    token = pending(client)
    with mock.patch.object(db_adapter, "mark_attendance", wraps=db_adapter.mark_attendance) as write:
        assert post(client, "/api/confirm/", {"confirm": "yes", "pending": "x" + token}).status_code == 400
        assert post(client, "/api/confirm/", {"confirm": "yes", "pending": {"student_id": "student-1"}}).status_code == 400
        other = django_user_model.objects.create_user(username="student-2")
        client.force_login(other)
        assert post(client, "/api/confirm/", {"confirm": "yes", "pending": token}).status_code == 403
        client.force_login(django_user_model.objects.get(username="student-1"))
        with mock.patch("api.services.authorize_request", return_value={"allowed": False}):
            assert post(client, "/api/confirm/", {"confirm": "yes", "pending": token}).status_code == 403
        write.assert_not_called()
        assert post(client, "/api/confirm/", {"confirm": "yes", "pending": token}).status_code == 409
        token = pending(client)
        assert post(client, "/api/confirm/", {"confirm": "yes", "pending": token}).status_code == 200
        client.logout()
        client.force_login(django_user_model.objects.get(username="student-1"))
        assert post(client, "/api/confirm/", {"confirm": "yes", "pending": token}).status_code == 409
        write.assert_called_once()
    with db_adapter._sqlite_connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM write_log").fetchone()[0] == 1

def test_cancel_consumes_confirmation_without_write(client):
    token = pending(client)
    with mock.patch.object(db_adapter, "mark_attendance") as write:
        assert post(client, "/api/confirm/", {"confirm": "no", "pending": token}).status_code == 200
        assert post(client, "/api/confirm/", {"confirm": "yes", "pending": token}).status_code == 409
        write.assert_not_called()

def test_real_write_disabled_at_backend_boundary(client, monkeypatch):
    token = pending(client)
    monkeypatch.setenv("VOXERP_USE_REAL_DB", "True")
    monkeypatch.setenv("VOXERP_OFFLINE_MODE", "False")
    with mock.patch.object(db_adapter, "mark_attendance") as write, mock.patch.object(db_adapter, "_get_connection") as connect:
        result = post(client, "/api/confirm/", {"confirm": "yes", "pending": token})
    assert result.status_code == 403
    assert "disabled" in result.json()["reply_text"]
    write.assert_not_called()
    connect.assert_not_called()

def test_policy_cannot_authorize_other_student(client):
    intent = {"action": "policy_query", "table": "policy", "filters": {"student_id": "student-2"}}
    assert not authorize_request("student-1", "student", intent, "student-2 attendance policy")["allowed"]
    with mock.patch.object(views.service.engine, "parse", return_value={"action": "policy_query", "table": "policy", "filters": {}}):
        with mock.patch.object(db_adapter, "get_attendance") as read:
            response = post(client, "/api/query/", {"text": "attendance policy"})
    assert response.status_code == 200
    read.assert_not_called()

def test_demo_users_and_confirm_identity(client):
    assert client.get("/users").json()["users"][0]["role"] == "student"
    from django.core import signing
    signed = signing.loads(pending(client), salt=views.PENDING_SALT)
    assert signed["pending"]["student_id"] == "student-1"

def test_sqlite_rollback_when_audit_fails(client):
    conn = db_adapter._sqlite_connect()
    try:
        conn.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON write_log BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(sqlite3.Error):
        db_adapter.mark_attendance("student-1", "DBMS", "2099-10-01", "absent", "student-1")
    conn = db_adapter._sqlite_connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM attendance WHERE attendance_date=?", ("2099-10-01",)).fetchone()[0] == 0
    finally:
        conn.close()


def test_gemma_output_validation_and_target_recovery():
    engine = IntentEngine(client=object())
    engine.gemma_available = True
    intent = engine._validate_intent({"action": "read", "table": "marks", "filters": {"student_id": 2}})
    assert intent["filters"]["student_id"] == "2"
    missing = engine._validate_intent({"action": "read", "table": "marks", "filters": {}})
    assert engine._apply_explicit_student_target("Show student 2 marks", missing)["filters"]["student_id"] == "2"
    with pytest.raises(ValueError):
        engine._extract_json_object("not JSON")
