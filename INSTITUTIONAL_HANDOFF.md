# VoxERP institutional handoff

**Handoff status: prepared for institutional review, not production authorization.**

## Operational status

- **Production: NOT READY.**
- **Demo: SUPERVISED READ-ONLY READY**, subject to local demo startup and the authorized clone being available. The present execution environment could not bind MariaDB to loopback port 3307, so live reads were not revalidated in this handoff run.
- **Writes: DISABLED.** Keep `VOXERP_ALLOW_REAL_WRITES=False`; the local ERP demo login is SELECT-only. Do not enable writes for production.
- **Physical voice acceptance: PENDING MANUAL TEST.**
- Django, local Gemma and the isolated MariaDB clone have historical validation records in [RELEASE_VALIDATION.md](RELEASE_VALIDATION.md). Those records are not evidence that the present checkout, model cache, physical devices, or institutional network were retested.

## Required college/ERP/infrastructure deliverables

Every item below is outstanding until an authorized owner provides and approves it. Do not put credentials or private academic data in Git.

1. **Authentication mapping — PENDING INSTITUTIONAL CONFIRMATION:** IdP, account lifecycle, MFA/session policy, provisioning and deprovisioning.
2. **ERP identity mapping — PENDING INSTITUTIONAL CONFIRMATION:** authenticated student/teacher/admin account to stable ERP identity, with uniqueness and change handling.
3. **Role mapping — PENDING INSTITUTIONAL CONFIRMATION:** authoritative role source and semantics; numeric IDs/designations alone are insufficient.
4. **Teacher scope — PENDING INSTITUTIONAL CONFIRMATION:** approved faculty primary-key mapping, student/course assignments, term validity, electives and allowed fields/operations.
5. **HOD identity and department — PENDING INSTITUTIONAL CONFIRMATION:** verified person, department boundary, acting appointments and validity.
6. **Admin capabilities — PENDING INSTITUTIONAL CONFIRMATION:** explicit academic permissions; technical superuser status must not imply academic authority.
7. **Operation permission matrix — PENDING INSTITUTIONAL CONFIRMATION:** per-role marks, attendance, timetable, policy, write, field and approval permissions.
8. **Revocation rules — PENDING INSTITUTIONAL CONFIRMATION:** source, propagation deadline, session/token invalidation and suspension behavior.
9. **Academic-term validity — PENDING INSTITUTIONAL CONFIRMATION:** official calendar, term identifiers, date boundaries and stale-scope rules.
10. **Official policy documents — PENDING INSTITUTIONAL CONFIRMATION:** approved corpus, owner, version, effective dates and permitted distribution.
11. **Production ERP connectivity — PENDING PRODUCTION ACCESS:** institution-approved private network path and firewall validation; never expose MariaDB publicly.
12. **Least-privilege service account — PENDING PRODUCTION ACCESS:** private credentials and read-only grants for the initial deployment.
13. **Hosting — PENDING INSTITUTIONAL CONFIRMATION:** approved host, operating system, runtime, capacity, backups and isolation.
14. **HTTPS/domain — PENDING INSTITUTIONAL CONFIRMATION:** domain, certificate, TLS termination, trusted proxy boundary and whether subdomain HSTS/preload is safe.
15. **Secret management — PENDING INSTITUTIONAL CONFIRMATION:** secret store, rotation, access policy and incident response; never commit secrets.
16. **Monitoring/logging — PENDING INSTITUTIONAL CONFIRMATION:** retention, redaction, alerting, access, privacy and incident contacts.
17. **Security approval — PENDING APPROVAL:** institutional security/data-protection review, threat model and vulnerability acceptance.
18. **Operational acceptance — PENDING APPROVAL:** named owner, support, outage/recovery runbook, rollback and manual voice acceptance if voice is required.
19. **Production deployment approval — PENDING APPROVAL:** explicit written release/deployment authorization and change window.

See [INSTITUTIONAL_AUTH_REQUIREMENTS.md](INSTITUTIONAL_AUTH_REQUIREMENTS.md) for the detailed fail-closed identity and permission contract and [DEPLOYMENT.md](DEPLOYMENT.md) for local demo and production-setting requirements.

## Institutional acceptance sequence

1. Supply the authoritative contracts and approved test identities without exposing real student data in the test artifact.
2. Complete access-control, revocation and denied-scope tests against a sanctioned isolated environment.
3. Provision private hosting, DNS/TLS, proxy trust, secrets, monitoring, backups and a read-only ERP account.
4. Run Django deployment checks (`manage.py check --deploy`) on the exact production configuration; resolve infrastructure-dependent warnings.
5. Validate production-network reads using an explicitly approved, read-only test plan. Never test by mutating real institutional records.
6. Complete attended browser microphone and speaker acceptance, if required.
7. Obtain security, operational and deployment approvals before any production release.

## Rollback and write boundary

The Git baseline `v1.0.0-validated` must remain unchanged. Rollback should select an institution-approved immutable release/commit and restore the separately maintained Django application database from an approved backup if required. ERP academic records are not a rollback mechanism and must not be modified by deployment. Keep production ERP grants read-only and `VOXERP_ALLOW_REAL_WRITES=False`. Do not push, deploy, connect to an unknown ERP, or change production data as part of this handoff.
