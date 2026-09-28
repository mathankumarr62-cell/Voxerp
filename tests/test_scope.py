import pytest

from intelligence.rbac import authorize_request
from intelligence.scope import (
    FacultyIdentity,
    RoleGrant,
    StaticScopeSource,
    StudentScope,
    VerifiedScopeResolver,
)


def resolver(*, role="teacher", operations=None, department_ids=frozenset({6}),
             all_departments=False, scopes=None, faculty_row_id=17):
    source = StaticScopeSource(
        identities=[FacultyIdentity("account", faculty_row_id, "employee", 6)],
        grants=[("account", RoleGrant(
            role,
            operations if operations is not None else frozenset({"marks"}),
            department_ids,
            all_departments,
        ))],
        scopes=scopes if scopes is not None else [
            StudentScope(
                "student-1",
                6,
                faculty_row_id=17,
                course_code="EE3020",
                section="A",
            )
        ],
    )
    return VerifiedScopeResolver(source)


def intent(*, student_id="student-1", table="marks", action="read",
           subject="EE3020", section="A"):
    return {
        "action": action,
        "table": table,
        "filters": {
            "student_id": student_id,
            "student_name": None,
            "subject": subject,
            "section": section,
        },
    }


def authorize(role="teacher", scope=None, request=None):
    return authorize_request(
        "account",
        role,
        request or intent(),
        "show student marks",
        scope_resolver=scope or resolver(role=role),
    )


def test_teacher_access_requires_verified_assignment_course_and_section():
    assert authorize()["reason"] == "verified_scope"
    assert authorize(request=intent(subject="OTHER"))["reason"] == "teaching_scope_denied"
    assert authorize(request=intent(section="B"))["reason"] == "teaching_scope_denied"
    assert authorize(request=intent(section=None))["reason"] == "teaching_scope_denied"


def test_teacher_employee_id_cannot_substitute_for_faculty_row_id():
    scope = resolver(faculty_row_id=1307)
    assert authorize(scope=scope)["reason"] == "teaching_scope_denied"


@pytest.mark.parametrize(
    ("scope", "reason"),
    [
        (resolver(scopes=[]), "target_unverified"),
        (resolver(operations=frozenset()), "role_unverified"),
        (
            resolver(scopes=[
                StudentScope("student-1", 35, faculty_row_id=17,
                             course_code="EE3020", section="A")
            ]),
            "department_denied",
        ),
        (
            resolver(all_departments=True),
            "department_denied",
        ),
    ],
)
def test_teacher_missing_or_out_of_scope_evidence_denied(scope, reason):
    assert authorize(scope=scope)["reason"] == reason


def test_hod_requires_explicit_department_grant():
    hod_scope = resolver(
        role="hod",
        scopes=[StudentScope("student-1", 6, course_code="EE3020")],
    )
    assert authorize(role="hod", scope=hod_scope)["reason"] == "verified_scope"

    outside = resolver(
        role="hod",
        department_ids=frozenset({35}),
        scopes=[StudentScope("student-1", 6, course_code="EE3020")],
    )
    assert authorize(role="hod", scope=outside)["reason"] == "department_denied"

    all_departments = resolver(
        role="hod",
        all_departments=True,
        scopes=[StudentScope("student-1", 6, course_code="EE3020")],
    )
    assert authorize(role="hod", scope=all_departments)["reason"] == "department_denied"


def test_admin_requires_explicit_all_department_grant():
    admin_scope = resolver(
        role="admin",
        all_departments=True,
        scopes=[StudentScope("student-1", 6, course_code="EE3020")],
    )
    assert authorize(role="admin", scope=admin_scope)["reason"] == "verified_scope"

    department_only = resolver(
        role="admin",
        scopes=[StudentScope("student-1", 6, course_code="EE3020")],
    )
    assert authorize(role="admin", scope=department_only)["reason"] == "department_scope_unknown"


@pytest.mark.parametrize("role", ["hod", "admin"])
def test_privileged_roles_without_resolver_remain_denied(role):
    decision = authorize_request("account", role, intent(), "show marks")
    assert decision["allowed"] is False
    assert decision["reason"] == "invalid_role"


def test_student_flow_is_unchanged_by_scope_resolver():
    decision = authorize_request(
        "student-1",
        "student",
        intent(student_id=None, subject=None, section=None),
        "show me my marks",
        scope_resolver=resolver(),
    )
    assert decision["allowed"] is True
    assert decision["target_student_id"] == "student-1"
