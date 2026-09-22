from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
import db_adapter
from api.identity import AuthenticatedIdentityResolver, current_student_is_active
from api.services import Identity, VoxERPService

@pytest.mark.parametrize("rows,allowed", [([(1,0)], True), ([(0,0)], False), ([(1,1)], False),
    ([], False), ([(1,0),(1,0)], False), ([(None,0)], False), ([("1","0")], False)])
def test_current_erp_status(rows, allowed, monkeypatch):
    monkeypatch.setenv("VOXERP_USE_REAL_DB", "True")
    conn = Mock(); conn.cursor.return_value.fetchall.return_value = rows
    with patch.object(db_adapter, "_get_connection", return_value=conn):
        assert current_student_is_active("123") is allowed
    assert conn.cursor.return_value.execute.call_args.args[1] == ("123",)
    conn.close.assert_called_once()

def test_status_failure_and_invalid_numeric_identity_fail_closed(monkeypatch):
    monkeypatch.setenv("VOXERP_USE_REAL_DB", "True")
    with patch.object(db_adapter, "_get_connection", side_effect=RuntimeError) as connect:
        assert not current_student_is_active("123x")
        connect.assert_not_called()
        assert not current_student_is_active("123")

@pytest.mark.parametrize("environment,mode,username,role", [
    ("development", "local_demo", "123", "student"),
    ("development", "local_demo", "123x", "unverified"),
    ("development", "", "123", "unverified"),
    ("production", "local_demo", "123", "unverified"),
])
def test_numeric_username_only_in_explicit_demo(environment, mode, username, role, monkeypatch):
    monkeypatch.setenv("VOXERP_USE_REAL_DB", "True")
    monkeypatch.setenv("VOXERP_ENV", environment)
    monkeypatch.setenv("VOXERP_IDENTITY_MODE", mode)
    user = SimpleNamespace(is_authenticated=True, is_active=True, is_superuser=False,
                           is_staff=False, username=username, groups=Mock())
    user.groups.values_list.return_value=[]
    assert AuthenticatedIdentityResolver().resolve(user).role == role

@pytest.mark.parametrize("active", [False, True])
def test_status_is_refreshed_before_academic_read(active):
    engine=Mock(); engine.parse.return_value={"action":"read", "table":"marks", "filters":{}}
    with patch("api.services.current_student_is_active", return_value=active), patch.object(db_adapter, "get_marks", return_value={"status":"no_data"}) as read:
        response=VoxERPService(engine).query(Identity("123", "student"), "Show my marks")
        assert read.called is active
        assert response["status"] == (200 if active else 403)

def test_denied_target_never_queries_erp_status():
    engine=Mock(); engine.parse.return_value={"action":"read", "table":"marks", "filters":{"student_id":"456"}}
    with patch("api.services.current_student_is_active") as status:
        VoxERPService(engine).query(Identity("123", "student"), "Show student 456 marks")
        status.assert_not_called()

def test_overall_attendance_calls_existing_daily_adapter():
    engine=Mock(); engine.parse.return_value={"action":"read", "table":"attendance", "filters":{}}
    with patch.object(db_adapter, "get_attendance", return_value={"status":"no_data"}) as read:
        VoxERPService(engine).query(Identity("123", "student"), "Show my attendance")
        read.assert_called_once_with("123", None)

def test_period_question_uses_hourly_records():
    engine=Mock(); engine.parse.return_value={"action":"read", "table":"attendance", "filters":{}}
    with patch.object(db_adapter, "get_attendance", return_value={"status":"no_data"}) as read:
        VoxERPService(engine).query(Identity("123", "student"), "How many periods was I absent?")
        read.assert_called_once_with("123", None, hourly=True)

def test_confirmation_refreshes_revocation():
    pending=dict(student_id="123", subject="COURSE", date="2026-01-01", status="absent", period=1)
    with patch("api.services.current_student_is_active", return_value=False), patch.object(db_adapter, "mark_attendance") as write:
        result=VoxERPService(Mock()).confirm(Identity("123", "student"), pending, "yes")
        assert result["status"] == 403
        write.assert_not_called()

@pytest.mark.parametrize("action,table", [("write", "marks"), ("delete", "attendance"), ("read", "students")])
def test_unconfigured_student_operations_denied(action, table):
    from intelligence.rbac import authorize_request
    assert not authorize_request("123", "student", {"action":action,"table":table,"filters":{}}, "Show my marks")["allowed"]

@pytest.mark.parametrize("target", [[], 123, {}, ""])
def test_malformed_target_never_becomes_self(target):
    from intelligence.rbac import authorize_request
    assert not authorize_request("123", "student", {"action":"read","table":"marks","filters":{"student_id":target}}, "Show my marks")["allowed"]

def test_default_gemma_load_pins_cached_revision(monkeypatch):
    import sys
    import intelligence.intent_engine as module
    loader=Mock(return_value=(object(), object()))
    monkeypatch.setitem(sys.modules, "mlx_vlm", SimpleNamespace(load=loader))
    monkeypatch.setattr(module, "GEMMA_MODEL_NAME", "mlx-community/gemma-4-e4b-it-4bit")
    with patch("huggingface_hub.snapshot_download", return_value="/cached/pinned-model") as download:
        assert module.IntentEngine().gemma_available
    assert download.call_args.kwargs["revision"] == "475b9088d29754a3379866cf5aeb6b41acd313c2"
    assert download.call_args.kwargs["local_files_only"] is True
    loader.assert_called_once_with("/cached/pinned-model")

@pytest.mark.parametrize("failed", [False, True])
def test_absence_question_recovery_after_local_inference(failed):
    from intelligence.intent_engine import IntentEngine
    engine=IntentEngine.__new__(IntentEngine)
    engine.gemma_available=True;engine.client=None
    engine._generate_gemma_intent=Mock(return_value=engine._fallback_intent())
    if failed:
        engine._generate_gemma_intent.side_effect=ValueError("invalid output")
    result=engine.parse("How many periods was I absent?", "student", {})
    assert result["action"] == "read" and result["table"] == "attendance"
    assert result["filters"]["student_id"] is None
    engine._generate_gemma_intent.assert_called_once()

@pytest.mark.parametrize("text", ["How many periods was student 2 absent?", "How many periods was I absent for student 2?", "How many periods was I absent yesterday?"])
def test_absence_recovery_never_discards_target_or_date(text):
    from intelligence.intent_engine import IntentEngine
    intent=IntentEngine._fallback_intent()
    assert IntentEngine._recover_absence_question(text, intent) == intent
