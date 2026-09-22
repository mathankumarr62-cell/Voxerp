# VoxERP — Institutional Authentication & Authorization Requirements

## Purpose

VoxERP currently supports authenticated student access and deliberately
fails closed for privileged Teacher/HOD/Admin access.

Before privileged academic access can be enabled in a college deployment,
the following facts must be supplied and verified by the institutional ERP
owner/IT team.

No passwords, API secrets, database root credentials, or private keys are
required for this contract.

---

## 1. Authenticated Identity

Document how the college ERP identifies the currently authenticated user.

### Student

Required:

- Authenticated account identifier
- Mapping to ERP student record
- Authoritative student ID / registration number
- Active/inactive status
- Rules for account revocation

Example contract:

    authenticated_user
        -> student_id
        -> student record

### Faculty

Required:

- Authenticated account identifier
- Mapping to ERP employee/faculty record
- Authoritative employee ID / faculty ID
- Active/inactive status
- Rules for account revocation

Example contract:

    authenticated_user
        -> employee_id
        -> faculty record

---

## 2. Authoritative Roles

Provide the authoritative role definitions used by the deployed ERP.

Required role meanings:

- STUDENT
- TEACHER / FACULTY
- HOD
- ADMIN

If the ERP uses numeric role IDs, provide their documented meanings.

Do NOT infer role meaning from:

- numeric IDs
- designation names
- usernames
- database row order
- observed examples

Role assignment must come from an authoritative deployment source.

---

## 3. Department Scope

Document how the ERP determines a user's academic department.

Required:

- Faculty -> department mapping
- HOD -> department mapping
- Department identifier format
- Active/inactive rules
- Effective dates, if applicable

---

## 4. Teacher Scope

Document exactly how a teacher's academic access is determined.

Required scope dimensions:

- Faculty identity
- Course/subject
- Section
- Batch
- Academic year
- Semester/term

Clarify whether access is based on:

- subject assignment
- section assignment
- class/advisor assignment
- mentor assignment
- enrollment
- another authoritative rule

For each operation, document whether it is permitted.

Examples:

- View marks
- View attendance
- View timetable
- Write attendance
- Modify marks
- View student profile
- Other ERP operations

If any scope dimension is missing or ambiguous, VoxERP must deny access.

---

## 5. HOD Scope

Document:

- HOD identity mapping
- HOD department
- Effective validity period
- Departments accessible
- Courses/sections accessible
- Permitted operations
- Whether access changes by academic year/semester

HOD access must not be inferred from a designation such as
"Head", "Professor", or "Principal".

---

## 6. Admin Scope

Document:

- Authoritative admin role
- Administrative capabilities
- Whether access is global or department-scoped
- Permitted operations
- Whether academic-record writes are allowed

"System Admin" or a similar designation must not automatically imply
unrestricted academic access.

---

## 7. Revocation and Validity

Document what happens when:

- Faculty changes department
- Faculty loses a course assignment
- Faculty changes role
- HOD assignment ends
- Employee becomes inactive
- Student becomes inactive
- Academic term changes

VoxERP must re-evaluate authorization using current authoritative data.

---

## 8. Required Authorization Rule

The deployment must satisfy:

    authenticated identity
        + authoritative role
        + valid scope
        + requested operation
        + valid target
        = ALLOW

Anything missing, ambiguous, malformed, expired, or revoked:

    DENY

---

## 9. Security Requirements

The following must remain unchanged:

- Student cannot access another student's private academic data.
- Client-supplied identity cannot override authenticated identity.
- HTTP headers cannot establish identity.
- Name-based matching cannot establish authorization.
- RAG/policy documents cannot bypass ERP authorization.
- Database queries cannot bypass RBAC.
- `/confirm` must re-authorize the operation.
- Failed or ambiguous authorization must fail closed.
- Production ERP writes remain disabled until explicitly approved.
- MariaDB must not be exposed publicly.

---

## 10. Information NOT Required

Do not send:

- Passwords
- Database root passwords
- API keys
- OAuth client secrets
- Private keys
- Session cookies
- Production authentication tokens

Only the authorization relationships and documented role/scope rules
are required.

---

## 11. Institutional Approval

The following should be confirmed by the authorized ERP/IT owner:

[ ] Authentication identity mapping verified

[ ] Student identity mapping verified

[ ] Faculty identity mapping verified

[ ] Role meanings verified

[ ] Department mapping verified

[ ] Teacher scope verified

[ ] HOD scope verified

[ ] Admin capabilities verified

[ ] Term/validity rules verified

[ ] Revocation rules verified

[ ] Permitted operations approved

[ ] Production integration owner identified

Name:

Role:

Date:

Approval/reference:

---

## Current VoxERP Status

Student access:
IMPLEMENTED AND VALIDATED

Teacher access:
FAIL-CLOSED pending authoritative institutional scope

HOD access:
FAIL-CLOSED pending authoritative institutional role/scope

Admin access:
FAIL-CLOSED pending authoritative institutional capability/scope

Production ERP integration:
PENDING institutional deployment access and approval


## Completion-audit evidence, 2026-09-22

The supplied dump's authentication users/groups/student-login tables are empty.
Employee and assignment joins exist, but they do not complete institutional
identity, role, operation and validity evidence. See SCHEMA_MAPPING.md's latest
audit and operation matrix. `api.identity.AuthenticatedIdentityResolver` is the
production integration point; production explicitly rejects the local numeric
username convention. Student active/discontinued state is refreshed before
real academic reads. Privileged integration remains fail-closed.
