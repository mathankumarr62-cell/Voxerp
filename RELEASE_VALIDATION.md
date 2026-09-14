# Person A Django integration validation

Integrated Person B 9a226d4 (which includes origin/main 5f5bbd4 and Person C fixes) with Person A c0b6243. No team remote was configured. The finalized db_adapter.py remains byte-for-byte unchanged from Person A; consolidated marks, hourly subject attendance, timetable course resolution, parameterized SQL and gated hourly writes remain intact. B intelligence/RBAC/RAG files remain unchanged.

Django is the permanent runtime. Retired runtime entrypoints were removed. Added service guards against production fixture data and disabled real writes, plus persistent atomic confirmation consumption across sessions/workers. Existing release/security tests were migrated to Django. Backups and manual transaction probes remain local, ignored and excluded from automatic collection.

Validation on 2026-09-14:
- Django check: no issues.
- Full pytest: 105 passed, 26 live MariaDB tests skipped; zero network/MariaDB attempts. Includes B tests, Django API, A adapter contracts and migrated release/security coverage.
- Read-only MariaDB validation: TCP, authentication, marks, subject attendance and timetable passed for approved historical validation inputs; IAT1/IAT2 expectations passed. Django service/RBAC/adapter reads and cross-student rejection passed. All sessions explicitly read-only, inference injected, no ERP write invoked.
- Local MLX runtime is unavailable (DEPENDENCY FAILURE). Actual Gemma inference was not validated; B's implementation remains unchanged.
- Installed dependency consistency passed. Google SDK emits a non-fatal Python 3.14 deprecation warning.

Tests cover authentication/CSRF, body/header identity spoofing, own reads, denied other/ambiguous targets, teacher fail-closed scope, policy isolation, signed/user-bound confirmations, cancellation, cross-session replay, reauthorization, disabled real writes before connection, generic errors, private-file denial and isolated SQLite rollback/audit/idempotency.

Deployment still requires migration of Django's separate application database and a supported Gemma host. No public database exposure was introduced. Remote Tailscale connectivity and firewall/public exposure were not certified by this local read check. Teacher access remains denied until a verified scope mapping exists. Production ERP writes were not tested or performed.
