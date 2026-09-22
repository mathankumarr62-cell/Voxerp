"""Fail-closed privileged scope resolution.

The application supplies verified deployment facts through ``ScopeSource``.
This module intentionally does not query the ERP or assign meanings to ERP
numeric role IDs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol, Sequence


READ_OPERATIONS = frozenset({"marks", "attendance", "timetable"})
WRITE_OPERATIONS = frozenset({"attendance_write"})
SUPPORTED_OPERATIONS = READ_OPERATIONS | WRITE_OPERATIONS
PRIVILEGED_ROLES = frozenset({"teacher", "hod", "admin"})


@dataclass(frozen=True)
class FacultyIdentity:
    account_id: str
    faculty_row_id: int
    employee_id: str
    department_id: int
    active: bool = True


@dataclass(frozen=True)
class RoleGrant:
    role: str
    operations: frozenset[str]
    department_ids: frozenset[int] = frozenset()
    all_departments: bool = False
    active: bool = True


@dataclass(frozen=True)
class StudentScope:
    student_id: str
    department_id: int
    faculty_row_id: Optional[int] = None
    course_id: Optional[int] = None
    course_code: Optional[str] = None
    batch: Optional[str] = None
    section: Optional[str] = None
    academic_year: Optional[str] = None
    year: Optional[str] = None
    semester: Optional[str] = None
    active: bool = True


@dataclass(frozen=True)
class ScopeDecision:
    allowed: bool
    reason: str
    message: str
    target_student_id: Optional[str] = None

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "message": self.message,
            "target_student_id": self.target_student_id,
        }


class ScopeSource(Protocol):
    """Read-only boundary implemented by a deployment integration."""

    def faculty_identity(self, account_id: str) -> Optional[FacultyIdentity]:
        ...

    def role_grant(self, account_id: str, role: str) -> Optional[RoleGrant]:
        ...

    def student_scope(self, student_id: str) -> Sequence[StudentScope]:
        ...


class VerifiedScopeResolver:
    """Authorize only from complete, deployment-supplied scope evidence."""

    def __init__(self, source: ScopeSource) -> None:
        self.source = source

    def authorize(
        self,
        account_id: str,
        role: str,
        operation: str,
        student_id: str,
        *,
        course_code: Optional[str] = None,
        section: Optional[str] = None,
    ) -> ScopeDecision:
        if not self._nonempty_string(account_id):
            return self._deny("missing_user", "I couldn't identify the current user.")
        if not self._nonempty_string(role):
            return self._deny("invalid_role", "I couldn't determine the user's role.")
        if not self._nonempty_string(operation) or operation not in SUPPORTED_OPERATIONS:
            return self._deny("unsupported_operation", "That academic operation is not configured.")
        if not self._nonempty_string(student_id):
            return self._deny("missing_target", "I couldn't identify the requested student.")
        if role.strip().lower() not in PRIVILEGED_ROLES:
            return self._deny("invalid_role", "I couldn't determine the user's role.")

        identity = self.source.faculty_identity(account_id.strip())
        if not self._valid_identity(identity, account_id.strip()):
            return self._deny("identity_unverified", "A verified ERP faculty identity is not configured.")

        grant = self.source.role_grant(account_id.strip(), role.strip().lower())
        if not self._valid_grant(grant, role.strip().lower(), operation):
            return self._deny("role_unverified", "A verified ERP role grant is not configured.")

        scopes = self.source.student_scope(student_id.strip())
        if not isinstance(scopes, Sequence) or isinstance(scopes, (str, bytes)):
            return self._deny("malformed_scope", "The verified ERP scope is malformed.", student_id)
        active_scopes = tuple(row for row in scopes if self._valid_student_scope(row))
        if not active_scopes:
            return self._deny("target_unverified", "The requested student scope could not be verified.", student_id)

        if role.strip().lower() == "teacher" and grant.all_departments:
            return self._deny("department_denied", "Teacher access requires explicit department scope.", student_id)
        if role.strip().lower() == "admin" and not grant.all_departments:
            return self._deny("department_scope_unknown", "Admin access requires explicit all-department scope.", student_id)

        if grant.all_departments:
            department_allowed = True
        elif grant.department_ids:
            department_allowed = all(row.department_id in grant.department_ids for row in active_scopes)
        else:
            return self._deny("department_scope_unknown", "No verified department scope is configured.", student_id)
        if not department_allowed:
            return self._deny("department_denied", "That student is outside the permitted department scope.", student_id)

        if role.strip().lower() == "teacher":
            if not self._nonempty_string(course_code):
                return self._deny("course_scope_unknown", "A verified course scope is required for teacher access.", student_id)
            matching = [
                row for row in active_scopes
                if row.faculty_row_id == identity.faculty_row_id
                and self._same(row.course_code, course_code)
                and self._nonempty_string(section)
                and self._nonempty_string(row.section)
                and row.section == section
            ]
            if not matching:
                return self._deny("teaching_scope_denied", "That student is outside the verified teaching scope.", student_id)

        return ScopeDecision(True, "verified_scope", "", student_id)

    @staticmethod
    def _valid_identity(identity: object, account_id: str) -> bool:
        return (
            isinstance(identity, FacultyIdentity)
            and identity.account_id == account_id
            and isinstance(identity.faculty_row_id, int)
            and not isinstance(identity.faculty_row_id, bool)
            and isinstance(identity.employee_id, str)
            and bool(identity.employee_id.strip())
            and isinstance(identity.department_id, int)
            and not isinstance(identity.department_id, bool)
            and identity.department_id > 0
            and identity.active is True
        )

    @staticmethod
    def _valid_grant(grant: object, role: str, operation: str) -> bool:
        return (
            isinstance(grant, RoleGrant)
            and grant.role.strip().lower() == role
            and grant.active is True
            and isinstance(grant.operations, frozenset)
            and grant.operations.issubset(SUPPORTED_OPERATIONS)
            and operation in grant.operations
            and isinstance(grant.department_ids, frozenset)
            and all(isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in grant.department_ids)
            and isinstance(grant.all_departments, bool)
        )

    @staticmethod
    def _valid_student_scope(scope: object) -> bool:
        return (
            isinstance(scope, StudentScope)
            and isinstance(scope.student_id, str)
            and bool(scope.student_id.strip())
            and isinstance(scope.department_id, int)
            and not isinstance(scope.department_id, bool)
            and scope.department_id > 0
            and scope.active is True
            and (scope.faculty_row_id is None or isinstance(scope.faculty_row_id, int))
            and (scope.course_code is None or (isinstance(scope.course_code, str) and bool(scope.course_code.strip())))
            and (scope.section is None or isinstance(scope.section, str))
        )

    @staticmethod
    def _same(left: Optional[str], right: str) -> bool:
        return isinstance(left, str) and left.strip().casefold() == right.strip().casefold()

    @staticmethod
    def _nonempty_string(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    @staticmethod
    def _deny(reason: str, message: str, student_id: Optional[str] = None) -> ScopeDecision:
        return ScopeDecision(False, reason, message, student_id)


class StaticScopeSource:
    """Deterministic source for tests and deployment wiring."""

    def __init__(
        self,
        identities: Iterable[FacultyIdentity] = (),
        grants: Iterable[tuple[str, RoleGrant]] = (),
        scopes: Iterable[StudentScope] = (),
    ) -> None:
        self._identities = {row.account_id: row for row in identities}
        self._grants = {(account, grant.role.strip().lower()): grant for account, grant in grants}
        rows: dict[str, list[StudentScope]] = {}
        for row in scopes:
            rows.setdefault(row.student_id, []).append(row)
        self._scopes = {student_id: tuple(values) for student_id, values in rows.items()}

    def faculty_identity(self, account_id: str) -> Optional[FacultyIdentity]:
        return self._identities.get(account_id)

    def role_grant(self, account_id: str, role: str) -> Optional[RoleGrant]:
        return self._grants.get((account_id, role.strip().lower()))

    def student_scope(self, student_id: str) -> Sequence[StudentScope]:
        return self._scopes.get(student_id, ())


__all__ = [
    "FacultyIdentity",
    "RoleGrant",
    "ScopeDecision",
    "ScopeSource",
    "StaticScopeSource",
    "StudentScope",
    "VerifiedScopeResolver",
]
