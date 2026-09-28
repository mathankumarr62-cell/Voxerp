"""Authorization must consume validated facts before academic database access."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import db_adapter
from api.services import Identity, VoxERPService
from intelligence.rbac import authorize_request
from intelligence.scope import FacultyIdentity, RoleGrant, StudentScope, VerifiedScopeResolver


def request(action="read", table="marks", **filters):
    return {"action": action, "table": table, "filters": filters}


def resolver(role="teacher"):
    source = SimpleNamespace(
        faculty_identity=Mock(return_value=FacultyIdentity("account", 17, "employee", 6)),
        role_grant=Mock(return_value=RoleGrant(role, frozenset({"marks"}),
                                             frozenset({6}), all_departments=role == "admin")),
        student_scope=Mock(return_value=[StudentScope("target", 6, faculty_row_id=17,
                                                     course_code="COURSE", section="A")]),
    )
    return VerifiedScopeResolver(source)


def decide(scope, role="teacher"):
    return scope.authorize("account", role, "marks", "target", course_code="COURSE", section="A")


@pytest.mark.parametrize("role", ["student", "teacher", "hod", "admin"])
@pytest.mark.parametrize("action,table", [("read", "marks"), ("policy_query", "policy")])
def test_name_target_never_queries_erp_to_establish_authority(role, action, table):
    with patch.object(db_adapter, "lookup_student", return_value={
        "status": "ok", "student": {"id": "account"}
    }) as lookup:
        result = authorize_request("account", role, request(action, table, student_name="Some Person"),
                                   "Show Some Person marks", scope_resolver=resolver(role))
    assert result["allowed"] is False
    lookup.assert_not_called()


def test_service_does_not_discover_schema_before_authorization():
    engine = Mock()
    engine.parse.return_value = request(student_id="other")
    with patch.object(db_adapter, "build_schema_map") as schema, patch.object(db_adapter, "get_marks") as read:
        result = VoxERPService(engine).query(Identity("self", "student"), "Show student other marks")
    assert "only access your own" in result["reply_text"]
    schema.assert_not_called()
    read.assert_not_called()


@pytest.mark.parametrize("role", ["teacher", "hod", "admin"])
def test_scope_evidence_must_belong_to_requested_student(role):
    scope = resolver(role)
    row = scope.source.student_scope.return_value[0]
    scope.source.student_scope.return_value = [replace(row, student_id="someone-else")]
    assert decide(scope, role).allowed is False


@pytest.mark.parametrize("bad_row", [None, {}, StudentScope("target", 0)])
def test_malformed_row_cannot_be_discarded_to_allow_remaining_evidence(bad_row):
    scope = resolver()
    scope.source.student_scope.return_value.append(bad_row)
    assert decide(scope).allowed is False


@pytest.mark.parametrize("faculty_id", [0, -1, True])
def test_invalid_faculty_primary_key_denied(faculty_id):
    scope = resolver()
    scope.source.faculty_identity.return_value = replace(scope.source.faculty_identity.return_value,
                                                         faculty_row_id=faculty_id)
    scope.source.student_scope.return_value = [replace(scope.source.student_scope.return_value[0],
                                                      faculty_row_id=faculty_id)]
    assert decide(scope).allowed is False


@pytest.mark.parametrize("role", [None, 2, "Professor", "System Admin"])
def test_malformed_or_designation_role_grant_denied(role):
    scope = resolver()
    scope.source.role_grant.return_value = replace(scope.source.role_grant.return_value, role=role)
    assert decide(scope).allowed is False


def test_hod_cannot_use_all_departments_to_bypass_department_scope():
    scope = resolver("hod")
    scope.source.role_grant.return_value = replace(scope.source.role_grant.return_value, all_departments=True)
    assert decide(scope, "hod").allowed is False


@pytest.mark.parametrize("boundary", ["faculty_identity", "role_grant", "student_scope"])
def test_unavailable_verified_source_denies(boundary):
    scope = resolver()
    getattr(scope.source, boundary).side_effect = RuntimeError("private deployment detail")
    decision = decide(scope)
    assert decision.allowed is False
    assert "private deployment detail" not in decision.message


@pytest.mark.parametrize("role", ["teacher", "hod", "admin"])
@pytest.mark.parametrize("boundary", ["faculty_identity", "role_grant", "student_scope"])
def test_revocation_rechecked_on_every_authorization(role, boundary):
    scope = resolver(role)
    assert decide(scope, role).allowed is True
    method = getattr(scope.source, boundary)
    if boundary == "student_scope":
        method.return_value = [replace(method.return_value[0], active=False)]
    else:
        method.return_value = replace(method.return_value, active=False)
    assert decide(scope, role).allowed is False


@pytest.mark.parametrize("filters", [[], "bad", 3])
def test_malformed_filters_denied(filters):
    result = authorize_request("self", "student", {"action": "read", "table": "marks", "filters": filters}, "my marks")
    assert result["allowed"] is False
