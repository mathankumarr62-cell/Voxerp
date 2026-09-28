# Institutional authentication and authorization requirements

**Status: PENDING INSTITUTIONAL CONFIRMATION.** VoxERP must not infer institutional roles or permissions from titles, numeric ERP role IDs, group names, class labels, or fuzzy identity matches. Until the college and ERP owner provide and approve the authoritative values below, unsupported and privileged academic requests must be denied.

## Required authoritative contract

| Area | College/ERP owner must provide | VoxERP safe behavior until confirmed |
| --- | --- | --- |
| Authentication | Approved identity provider, login lifecycle, MFA/session requirements, account provisioning/deprovisioning | Use only the separately provisioned local demo accounts; no institutional authentication is claimed |
| Student identity | Stable authenticated-account-to-ERP-student-ID mapping, uniqueness and change handling | Student self-access only through the local demo mapping; reject unresolved or conflicting identity |
| Teacher identity | Authenticated account to verified faculty primary key/employee record mapping | Deny teacher academic data |
| Role mapping | Authoritative source and semantics for student, teacher, HOD and administrator; effective dates | Unknown/missing roles deny |
| Teacher scope | Approved student/course relationship (teaching assignment, enrollment status, electives, cross-department rules and term validity) | Deny teacher academic data |
| HOD scope | Verified HOD identity, department boundary, acting appointments and validity | Deny HOD academic data |
| Admin capabilities | Named academic operations, fields, boundaries and approvals; distinguish technical administration from academic authority | Deny academic operations; Django superuser is not academic authorization |
| Operation matrix | Read/write per role and operation (marks, attendance, timetable, policy), field restrictions, approval requirements | Deny anything not explicitly allowed |
| Writes | Authorized isolated test database, approved mutation schema and audit/rollback requirements | `VOXERP_ALLOW_REAL_WRITES=False`; no real or production writes |
| Revocation | Source of truth, propagation SLA, cache/session invalidation, termination and suspension rules | Revalidate through the approved source before any future privileged access |
| Academic validity | Official academic term/calendar, effective dates and stale enrollment behavior | No term or authorization inferred |
| Policy corpus | Approved current policies, owner, version/effective date, review/expiry and distribution permission | Only repository demonstration policy text; do not represent as authoritative college policy |

## Required evidence and approvals

Provide a versioned, owner-approved mapping and permission matrix, test identities covering both allowed and denied scope, revocation test cases, a data-protection/security review, operational monitoring and incident contacts, and written approval for each environment. Do not include production passwords, tokens, student records, or database dumps in source control or this document.

Institutional identity mapping, teacher/HOD/Admin grants, operation permissions, revocation rules and official policy documents are all **PENDING INSTITUTIONAL CONFIRMATION**. Production network access and a least-privilege service identity are **PENDING PRODUCTION ACCESS**. Security, operational and deployment approvals are **PENDING APPROVAL**. No value in this document should be replaced by a guess.
