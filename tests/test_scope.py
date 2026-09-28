import pytest

from intelligence.rbac import authorize_request
from intelligence.scope import (
    FacultyIdentity,
    RoleGrant,
    StaticScopeSource,
    StudentScope,
    VerifiedScopeResolver,
)


def resolver(
    *,
    identities=(),
    grants=(),
    scopes=(),
):
    return VerifiedScopeResolver(StaticScopeSource(identities, grants, scopes))


def teacher_resolver(**overrides):
    values = {
        "identities": [FacultyIdentity("teacher-account", 17, "1307", 6)],
        "grants": [
            (
                "teacher-account",
                RoleGrant("teacher", frozenset({"marks", "attendance"}), frozenset({6})),
            )
        ],
        "scopes": [
            StudentScope("student-1", 6, course_id=285, course_code="EE3020", faculty_row_id=17)
        ],
    }
    values.update(overrides)
    return resolver(**values)


def intent(table="marks", action="read", student_id="student-1", subject=None):
    return {
        "action": action,
        "table": table,
        "filters": {"student_id": student_id, "student_name": None, "subject": subject},
    }


def test_teacher_is_allowed_only_for_verified_faculty_assignment_and_course():
    decision = authorize_request(
        "teacher-account",
        "teacher",
        intent(subject="EE3020"),
        "show student marks",
        scope_resolver=teacher_resolver(),
    )
    assert decision["allowed"] is True
    assert decision["reason"] == "verified_scope"

    wrong_course = authorize_request(
        "teacher-account",
        "teacher",
        intent(subject="OTHER"),
        "show student marks",
        scope_resolver=teacher_resolver(),
    )
    assert wrong_course["reason"] == "teaching_scope_denied"


def test_teacher_without_course_scope_is_denied_for_course_data():
    decision = authorize_request(
        "teacher-account",
        "teacher",
        intent(),
        "show student marks",
        scope_resolver=teacher_resolver(),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "course_scope_unknown"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"identities": []}, "identity_unverified"),
        (
            {
                "grants": [
                    (
                        "teacher-account",
                        RoleGrant("teacher", frozenset({"marks"}), frozenset({6}), active=False),
                    )
                ]
            },
            "role_unverified",
        ),
        (
            {
                "grants": [
                    (
                        "teacher-account",
                        RoleGrant("teacher", frozenset({"attendance"}), frozenset({6})),
                    )
                ]
            },
            "operation_denied",
        ),
        ({"scopes": []}, "target_unverified"),
        (
            {
                "grants": [
                    (
                        "teacher-account",
                        RoleGrant("teacher", frozenset({"marks"}), frozenset()),
                    )
                ]
            },
            "department_scope_unknown",
        ),
        (
            {
                "grants": [
                    (
                        "teacher-account",
                        RoleGrant("teacher", frozenset({"marks"}), frozenset({35})),
                    )
                ]
            },
            "department_denied",
        ),
    ],
)
def test_teacher_scope_fail_closed(change, reason):
    base = {
        "identities": [FacultyIdentity("teacher-account", 17, "1307", 6)],
        "grants": [
            (
                "teacher-account",
                RoleGrant("teacher", frozenset({"marks"}), frozenset({6})),
            )
        ],
        "scopes": [StudentScope("student-1", 6, course_code="EE3020", faculty_row_id=17)],
    }
    base.update(change)
    decision = authorize_request(
        "teacher-account",
        "teacher",
        intent(subject="EE3020"),
        "show student marks",
        scope_resolver=resolver(**base),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == reason


def test_teacher_cannot_use_employee_id_as_faculty_row_id():
    scope = resolver(
        identities=[FacultyIdentity("teacher-account", 1307, "1307", 6)],
        grants=[("teacher-account", RoleGrant("teacher", frozenset({"marks"}), frozenset({6})))],
        scopes=[StudentScope("student-1", 6, course_code="EE3020", faculty_row_id=17)],
    )
    decision = authorize_request(
        "teacher-account", "teacher", intent(subject="EE3020"), scope_resolver=scope
    )
    assert decision["reason"] == "teaching_scope_denied"


def test_hod_requires_explicit_role_and_department_scope():
    scope = resolver(
        identities=[FacultyIdentity("hod-account", 106, "1406", 35)],
        grants=[("hod-account", RoleGrant("hod", frozenset({"marks", "attendance"}), frozenset({35})))],
        scopes=[StudentScope("student-1", 35, course_code="EC25C05", faculty_row_id=106)],
    )
    allowed = authorize_request("hod-account", "hod", intent(), scope_resolver=scope)
    assert allowed["allowed"] is True

    outside = authorize_request(
        "hod-account",
        "hod",
        intent(student_id="student-2"),
        scope_resolver=resolver(
            identities=[FacultyIdentity("hod-account", 106, "1406", 35)],
            grants=[("hod-account", RoleGrant("hod", frozenset({"marks"}), frozenset({35})))],
            scopes=[StudentScope("student-2", 6, course_code="EE3020", faculty_row_id=17)],
        ),
    )
    assert outside["reason"] == "department_denied"


def test_admin_requires_explicit_all_department_grant():
    scope = resolver(
        identities=[FacultyIdentity("admin-account", 280, "2501", 39)],
        grants=[("admin-account", RoleGrant("admin", frozenset({"marks"}), all_departments=True))],
        scopes=[StudentScope("student-1", 6, course_code="EE3020", faculty_row_id=17)],
    )
    decision = authorize_request("admin-account", "admin", intent(), scope_resolver=scope)
    assert decision["allowed"] is True


@pytest.mark.parametrize("role", ["hod", "admin"])
def test_privileged_roles_without_resolver_remain_denied(role):
    decision = authorize_request("account", role, intent(), "show marks")
    assert decision["allowed"] is False
    assert decision["reason"] == "invalid_role"


def test_student_flow_does_not_use_scope_resolver():
    decision = authorize_request(
        "student-1",
        "student",
        intent(student_id=None),
        "show me my marks",
        scope_resolver=teacher_resolver(),
    )
    assert decision["allowed"] is True
    assert decision["target_student_id"] == "student-1"
