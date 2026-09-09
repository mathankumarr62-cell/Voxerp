import copy
import sqlite3
from unittest import mock

import pytest
import app
import db_adapter
from intelligence.intent_engine import IntentEngine
from intelligence.rbac import authorize_request


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db_adapter, "_DB_FILE", str(tmp_path / "fixture.db"))
    db_adapter.initialize_database()
    monkeypatch.setenv("VOXERP_ENV", "production")
    monkeypatch.setenv("VOXERP_TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
    monkeypatch.setenv("VOXERP_PENDING_SECRET", "release-test-only")
    monkeypatch.setattr(app, "intent_engine", IntentEngine(client=object()))
    return app.app.test_client()


def headers(student="student-1", principal="principal-1"):
    return {"X-Forwarded-User": principal, "X-Forwarded-Student-Id": student,
            "X-Forwarded-Groups": "voxerp-students"}


def test_own_reads_and_body_identity_cannot_override(client):
    for text, expected in [("Show my DBMS marks", "88"), ("Show my timetable", "Monday"),
                           ("Show my DBMS attendance", "present")]:
        response = client.post("/query", headers=headers(), json={"text": text,
            "student_id": "student-2", "user_id": "student-2", "role": "teacher"})
        assert response.status_code == 200
        assert expected in response.json["reply_text"]


def test_cross_student_denied_before_read(client):
    with mock.patch.object(db_adapter, "get_marks") as read:
        response = client.post("/query", headers=headers(), json={"text": "Show another student's marks"})
    assert response.status_code == 403
    read.assert_not_called()


@pytest.mark.parametrize("path", ["/.env", "/voxerp.db", "/db_adapter.py", "/app.py", "/requirements.txt", "/.git/config"])
def test_private_files_not_served(client, path):
    assert client.get(path).status_code == 404
    assert client.get("/").status_code == 200


def test_signed_confirmation_reauthorization_and_idempotency(client):
    request = client.post("/query", headers=headers(), json={"text": "Mark my DBMS attendance absent period 2"})
    assert request.status_code == 200
    token = request.json["confirmation_token"]
    with mock.patch.object(db_adapter, "mark_attendance", wraps=db_adapter.mark_attendance) as write:
        no = client.post("/confirm", headers=headers(), json={"confirm": "no", "confirmation_token": token})
        assert no.status_code == 200
        write.assert_not_called()
        forged = client.post("/confirm", headers=headers(), json={"confirm": "yes", "pending": {"student_id": "student-1"}})
        assert forged.status_code == 400
        tampered = client.post("/confirm", headers=headers(), json={"confirm": "yes", "confirmation_token": "x" + token})
        assert tampered.status_code == 400
        other = client.post("/confirm", headers=headers("student-2", "principal-2"), json={"confirm": "yes", "confirmation_token": token})
        assert other.status_code == 403
        write.assert_not_called()
        with mock.patch.object(app, "authorize_request", return_value={"allowed": False}):
            assert client.post("/confirm", headers=headers(), json={"confirm": "yes", "confirmation_token": token}).status_code == 403
        write.assert_not_called()
        for _ in range(2):
            assert client.post("/confirm", headers=headers(), json={"confirm": "yes", "confirmation_token": token}).status_code == 200
    conn = db_adapter._sqlite_connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM write_log").fetchone()[0] == 1
    finally:
        conn.close()


def test_real_write_disabled_at_backend_boundary(client, monkeypatch):
    response = client.post("/query", headers=headers(), json={"text": "Mark my DBMS attendance absent period 2"})
    monkeypatch.setenv("VOXERP_USE_REAL_DB", "True")
    with mock.patch.object(db_adapter, "mark_attendance") as write:
        result = client.post("/confirm", headers=headers(), json={"confirm": "yes", "confirmation_token": response.json["confirmation_token"]})
    assert "disabled" in result.json["reply_text"]
    write.assert_not_called()


def test_policy_cannot_authorize_other_student(client):
    intent = {"action": "policy_query", "table": "policy", "filters": {"student_id": "student-2"}}
    assert not authorize_request("student-1", "student", intent, "student-2 attendance policy")["allowed"]
    with mock.patch.object(app, "parse_intent", return_value={"action": "policy_query", "table": "policy", "filters": {}}):
        with mock.patch.object(db_adapter, "get_attendance") as read:
            response = client.post("/query", headers=headers(), json={"text": "attendance policy"})
    assert response.status_code == 200
    read.assert_not_called()


def test_demo_users_and_confirm_identity(client, monkeypatch):
    monkeypatch.setenv("VOXERP_ENV", "development")
    monkeypatch.setenv("VOXERP_AUTH_MODE", "demo")
    assert client.get("/users").status_code == 200
    response = client.post("/query", json={"user_id": "student-1", "role": "teacher", "text": "Mark my DBMS attendance absent period 2"})
    pending = app._load_confirmation_token(response.json["confirmation_token"])
    assert pending["actor_role"] == "student"
    assert client.post("/confirm", json={"user_id": "student-1", "confirm": "yes", "confirmation_token": response.json["confirmation_token"]}).status_code == 200


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


def test_missing_proxy_student_mapping_denied(client):
    hdr = headers()
    del hdr["X-Forwarded-Student-Id"]
    assert client.get("/me", headers=hdr).status_code == 401


def test_gemma_output_validation_and_target_recovery():
    engine = IntentEngine(client=object())
    engine.gemma_available = True
    intent = engine._validate_intent({"action": "read", "table": "marks", "filters": {"student_id": 2}})
    assert intent["filters"]["student_id"] == "2"
    missing = engine._validate_intent({"action": "read", "table": "marks", "filters": {}})
    assert engine._apply_explicit_student_target("Show student 2 marks", missing)["filters"]["student_id"] == "2"
    with pytest.raises(ValueError):
        engine._extract_json_object("not JSON")
