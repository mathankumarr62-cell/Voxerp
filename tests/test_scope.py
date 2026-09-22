import pytest

from intelligence.rbac import authorize_request
from intelligence.scope import (
    FacultyIdentity,
    RoleGrant,
    StaticScopeSource,
    StudentScope,
    VerifiedScopeResolver,
)


def make_resolver(*, identities=(), grants=(), scopes=()):
    return VerifiedScopeResolver(StaticScopeSource(identities, grants, scopes))


def teacher_resolver():
    return make_resolver(
        identities=[FacultyIdentity("teacher-account", 17, "1307", 6)],
        grants=[("teacher-account", RoleGrant("teacher", frozenset({"marks"}), frozenset({6})))],
        scopes=[
            StudentScope(
                "student-1",
                6,
                faculty_row_id=17,
                course_id=285,
                course_code="EE3020",
                batch="2023",
                section="A",
            )
        ],
    )


def intent(*, student_id="student-1", table="marks", action="read", subject=None, section=None):
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


def authorize_privileged(role, resolver, request=None):
    return authorize_request(
        "teacher-account",
        role,
        request or intent(subject="EE3020", section="A"),
        "show the student's marks",
        scope_resolver=resolver,
    )


def test_teacher_assigned_course_is_allowed():
    result = authorize_privileged("teacher", teacher_resolver())
    assert result["allowed"] is True
    assert result["reason"] == "verified_scope"


@pytest.mark.parametrize(
    ("scope_change", "request_change", "reason"),
    [
        (None, {"subject": "OTHER"}, "teaching_scope_denied"),
        (None, {"section": "B"}, "teaching_scope_denied"),
        (
            [StudentScope("student-1", 35, faculty_row_id=17, course_code="EE3020", section="A")],
            {"subject": "EE3020"},
            "department_denied",
        ),
    ],
)
def test_teacher_unassigned_course_wrong_section_and_department_denied(
    scope_change, request_change, reason
):
    resolver = teacher_resolver()
    if scope_change is not None:
        resolver = make_resolver(
            identities=[FacultyIdentity("teacher-account", 17, "1307", 6)],
            grants=[("teacher-account", RoleGrant("teacher", frozenset({"marks"}), frozenset({6})))],
            scopes=scope_change,
        )
    request = intent(subject=request_change.get("subject", "EE3020"), section=request_change.get("section", "A"))
    assert authorize_privileged("teacher", resolver, request)["reason"] == reason


def test_teacher_missing_identity_denied():
    resolver = make_resolver(
        grants=[("teacher-account", RoleGrant("teacher", frozenset({"marks"}), frozenset({6})))],
        scopes=[StudentScope("student-1", 6, faculty_row_id=17, course_code="EE3020")],
    )
    assert authorize_privileged("teacher", resolver)["reason"] == "identity_unverified"


def test_teacher_missing_operation_grant_denied():
    resolver = make_resolver(
        identities=[FacultyIdentity("teacher-account", 17, "1307", 6)],
        grants=[("teacher-account", RoleGrant("teacher", frozenset(), frozenset({6})))],
        scopes=[StudentScope("student-1", 6, faculty_row_id=17, course_code="EE3020")],
    )
    assert authorize_privileged("teacher", resolver)["reason"] == "role_unverified"


def test_hod_own_department_allowed_and_other_department_denied():
    resolver = make_resolver(
        identities=[FacultyIdentity("hod-account", 106, "1406", 35)],
        grants=[("hod-account", RoleGrant("hod", frozenset({"marks"}), frozenset({35})))],
        scopes=[
            StudentScope("own", 35, course_code="EC25C05"),
            StudentScope("other", 6, course_code="EE3020"),
        ],
    )
    own = authorize_request("hod-account", "hod", intent(student_id="own"), scope_resolver=resolver)
    other = authorize_request("hod-account", "hod", intent(student_id="other"), scope_resolver=resolver)
    assert own["allowed"] is True
    assert other["reason"] == "department_denied"


def test_hod_missing_grant_and_department_scope_denied():
    identity = [FacultyIdentity("hod-account", 106, "1406", 35)]
    scope = [StudentScope("student-1", 35, course_code="EC25C05")]
    no_grant = make_resolver(identities=identity, scopes=scope)
    no_department = make_resolver(
        identities=identity,
        grants=[("hod-account", RoleGrant("hod", frozenset({"marks"}), frozenset()))],
        scopes=scope,
    )
    assert authorize_request("hod-account", "hod", intent(), scope_resolver=no_grant)["reason"] == "role_unverified"
    assert authorize_request("hod-account", "hod", intent(), scope_resolver=no_department)["reason"] == "department_scope_unknown"


def test_admin_explicit_capability_allowed_unspecified_capability_denied():
    resolver = make_resolver(
        identities=[FacultyIdentity("admin-account", 280, "2501", 39)],
        grants=[("admin-account", RoleGrant("admin", frozenset({"marks"}), all_departments=True))],
        scopes=[StudentScope("student-1", 6, course_code="EE3020")],
    )
    allowed = authorize_request("admin-account", "admin", intent(), scope_resolver=resolver)
    denied = authorize_request(
        "admin-account",
        "admin",
        intent(table="attendance", subject="EE3020"),
        scope_resolver=resolver,
    )
    assert allowed["allowed"] is True
    assert denied["reason"] == "role_unverified"


@pytest.mark.parametrize("departments", [frozenset(), frozenset({6})])
def test_admin_missing_all_department_scope_denied(departments):
    resolver = make_resolver(
        identities=[FacultyIdentity("admin-account", 280, "2501", 39)],
        grants=[("admin-account", RoleGrant("admin", frozenset({"marks"}), departments))],
        scopes=[StudentScope("student-1", 6, course_code="EE3020")],
    )
    assert authorize_request("admin-account", "admin", intent(), scope_resolver=resolver)["reason"] == "department_scope_unknown"


@pytest.mark.parametrize("role", ["unknown", "", "2", "29"])
def test_unknown_role_denied(role):
    result = authorize_request("account", role, intent(), scope_resolver=teacher_resolver())
    assert result["allowed"] is False
    assert result["reason"] == "invalid_role"


def test_missing_target_and_malformed_scope_denied():
    missing_target = authorize_request(
        "teacher-account",
        "teacher",
        intent(student_id=None),
        scope_resolver=teacher_resolver(),
    )
    malformed = make_resolver(
        identities=[FacultyIdentity("teacher-account", 17, "1307", 6)],
        grants=[("teacher-account", RoleGrant("teacher", frozenset({"marks"}), frozenset({6})))],
    )
    malformed.source.student_scope = lambda student_id: "not-a-scope"
    assert missing_target["reason"] == "ambiguous_target"
    assert authorize_privileged("teacher", malformed)["reason"] == "malformed_scope"


def test_student_authorization_is_unchanged_with_resolver():
    result = authorize_request(
        "student-1",
        "student",
        intent(student_id=None),
        "show me my marks",
        scope_resolver=teacher_resolver(),
    )
    assert result["allowed"] is True
    assert result["target_student_id"] == "student-1"


@pytest.mark.parametrize("role", ["hod", "admin"])
def test_no_resolver_keeps_privileged_roles_denied(role):
    result = authorize_request("account", role, intent(), "show marks")
    assert result["allowed"] is False
    assert result["reason"] == "invalid_role"


@pytest.mark.parametrize(
    ("all_departments", "departments", "target_department", "allowed"),
    [
        (True, frozenset(), 35, False),
        (True, frozenset({6}), 6, False),
        (False, frozenset({6}), 6, True),
        (False, frozenset({6}), 35, False),
        (False, frozenset(), 6, False),
    ],
)
def test_teacher_requires_explicit_matching_department(
    all_departments, departments, target_department, allowed
):
    resolver = make_resolver(
        identities=[FacultyIdentity("teacher-account", 17, "1307", 6)],
        grants=[("teacher-account", RoleGrant(
            "teacher", frozenset({"marks"}), departments, all_departments=all_departments
        ))],
        scopes=[StudentScope("student-1", target_department, faculty_row_id=17,
                             course_code="EE3020", section="A")],
    )
    assert authorize_privileged("teacher", resolver)["allowed"] is allowed


@pytest.mark.parametrize("sections", [("A",), ("A", "B"), (None,), ("",)])
@pytest.mark.parametrize("requested_section", [None, "", "A", "C"])
def test_teacher_requires_verified_matching_section(sections, requested_section):
    resolver = make_resolver(
        identities=[FacultyIdentity("teacher-account", 17, "1307", 6)],
        grants=[("teacher-account", RoleGrant("teacher", frozenset({"marks"}), frozenset({6})))],
        scopes=[StudentScope("student-1", 6, faculty_row_id=17,
                             course_code="EE3020", section=section) for section in sections],
    )
    result = authorize_privileged(
        "teacher", resolver, intent(subject="EE3020", section=requested_section)
    )
    assert result["allowed"] is (requested_section == "A" and "A" in sections)


@pytest.mark.parametrize("faculty_row_id", [None, 18])
def test_teacher_requires_matching_faculty_assignment(faculty_row_id):
    resolver = make_resolver(
        identities=[FacultyIdentity("teacher-account", 17, "1307", 6)],
        grants=[("teacher-account", RoleGrant("teacher", frozenset({"marks"}), frozenset({6})))],
        scopes=[StudentScope("student-1", 6, faculty_row_id=faculty_row_id,
                             course_code="EE3020", section="A")],
    )
    assert authorize_privileged("teacher", resolver)["allowed"] is False
