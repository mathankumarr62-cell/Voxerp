"""Verified ERP scope resolution primitives.

This module deliberately contains no database access and no default role
mapping. A deployment must supply the authenticated-account binding, semantic
role grant, and verified ERP relationship rows before privileged access can be
allowed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol, Sequence


READ_OPERATIONS = frozenset({"marks", "attendance", "timetable"})
WRITE_OPERATIONS = frozenset({"attendance_write"})


@dataclass(frozen=True)
class FacultyIdentity:
    account_id: str
    faculty_row_id: int
    employee_id: str
    department_id: int
    active: bool = True


@dataclass(frozen=True)
class RoleGrant:
    """A deployment-supplied semantic role and its explicit boundaries."""

    role: str
    operations: frozenset[str]
    department_ids: frozenset[int] = frozenset()
    all_departments: bool = False
    active: bool = True


@dataclass(frozen=True)
class StudentScope:
    student_id: str
    department_id: int
    course_id: Optional[int] = None
    course_code: Optional[str] = None
    faculty_row_id: Optional[int] = None
    academic_year: Optional[str] = None
    year: Optional[str] = None
    semester: Optional[str] = None
    section: Optional[str] = None
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
    """Read-only deployment boundary for verified identity and scope data."""

    def faculty_identity(self, account_id: str) -> Optional[FacultyIdentity]:
        ...

    def role_grant(self, account_id: str, role: str) -> Optional[RoleGrant]:
        ...

    def student_scope(self, student_id: str) -> Sequence[StudentScope]:
        ...


class VerifiedScopeResolver:
    """Resolve privileged academic scope without guessing missing relationships."""

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
    ) -> ScopeDecision:
        if not isinstance(account_id, str) or not account_id.strip():
            return self._deny("missing_user", "I couldn't identify the current user.")
        if not isinstance(role, str) or not role.strip():
            return self._deny("invalid_role", "I couldn't determine the user's role.")
        if not isinstance(student_id, str) or not student_id.strip():
            return self._deny("missing_target", "I couldn't identify the requested student.")
        if operation not in READ_OPERATIONS | WRITE_OPERATIONS:
            return self._deny("unsupported_operation", "That academic operation is not configured.")

        identity = self.source.faculty_identity(account_id.strip())
        if identity is None or not identity.active:
            return self._deny("identity_unverified", "A verified ERP faculty identity is not configured.")

        grant = self.source.role_grant(account_id.strip(), role.strip().lower())
        if grant is None or not grant.active:
            return self._deny("role_unverified", "A verified ERP role grant is not configured.")
        if grant.role.strip().lower() != role.strip().lower():
            return self._deny("role_mismatch", "The verified ERP role does not match this request.")
        if operation not in grant.operations:
            return self._deny("operation_denied", "That operation is not permitted for this role.")

        scopes = tuple(row for row in self.source.student_scope(student_id.strip()) if row.active)
        if not scopes:
            return self._deny("target_unverified", "The requested student scope could not be verified.", student_id)

        if grant.all_departments:
            permitted = True
        elif grant.department_ids:
            permitted = all(row.department_id in grant.department_ids for row in scopes)
        else:
            return self._deny("department_scope_unknown", "No verified department scope is configured.")

        if not permitted:
            return self._deny("department_denied", "That student is outside the permitted department scope.", student_id)

        if role.strip().lower() == "teacher":
            if operation in {"marks", "attendance", "attendance_write"} and not course_code:
                return self._deny(
                    "course_scope_unknown",
                    "A verified course scope is required for teacher access.",
                    student_id,
                )
            matching = [
                row for row in scopes
                if row.faculty_row_id == identity.faculty_row_id
                and (course_code is None or self._course_matches(row, course_code))
            ]
            if not matching:
                return self._deny("teaching_scope_denied", "That student is outside the verified teaching scope.", student_id)

        return ScopeDecision(True, "verified_scope", "", student_id)

    @staticmethod
    def _course_matches(scope: StudentScope, course_code: str) -> bool:
        return (
            isinstance(scope.course_code, str)
            and scope.course_code.strip().casefold() == course_code.strip().casefold()
        )

    @staticmethod
    def _deny(reason: str, message: str, student_id: Optional[str] = None) -> ScopeDecision:
        return ScopeDecision(False, reason, message, student_id)


class StaticScopeSource:
    """Small immutable source useful for deployment adapters and tests."""

    def __init__(
        self,
        identities: Iterable[FacultyIdentity] = (),
        grants: Iterable[tuple[str, RoleGrant]] = (),
        scopes: Iterable[StudentScope] = (),
    ) -> None:
        self._identities = {row.account_id: row for row in identities}
        self._grants = {(account_id, grant.role.strip().lower()): grant for account_id, grant in grants}
        scope_rows: dict[str, list[StudentScope]] = {}
        for row in scopes:
            scope_rows.setdefault(row.student_id, []).append(row)
        self._scopes = {student_id: tuple(rows) for student_id, rows in scope_rows.items()}

    def faculty_identity(self, account_id: str) -> Optional[FacultyIdentity]:
        return self._identities.get(account_id)

    def role_grant(self, account_id: str, role: str) -> Optional[RoleGrant]:
        return self._grants.get((account_id, role.strip().lower()))

    def student_scope(self, student_id: str) -> Sequence[StudentScope]:
        return tuple(self._scopes.get(student_id, ()))


__all__ = [
    "FacultyIdentity",
    "RoleGrant",
    "ScopeDecision",
    "ScopeSource",
    "StaticScopeSource",
    "StudentScope",
    "VerifiedScopeResolver",
]
