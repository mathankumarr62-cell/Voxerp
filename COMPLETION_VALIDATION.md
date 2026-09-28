# VoxERP completion validation

**Current validation pass: 2026-09-28.** This report distinguishes checks run against the current checkout from historical acceptance evidence. A previous result is not treated as a present run.

## Current checkout evidence

| Check | Current result |
| --- | --- |
| Checkout | `/Users/vijayaguru/Desktop/Voxerp`, branch `fix/gemma-entity-recovery`, HEAD `862782d`; existing worktree changes were preserved |
| Django system check | `manage.py check`: passed after security settings changes |
| Migration consistency | `manage.py makemigrations --check --dry-run`: no changes detected |
| Changed-area regressions | 25 passed: local-demo guard, production security settings/password policy, lazy Gemma service lifecycle, verified scopes |
| Python compilation | `compileall -q api intelligence rag tests scripts manage.py conftest.py`: passed |
| Worktree formatting | `git diff --check`: passed |
| Full pytest suite | **153 passed, 26 skipped in 11.56s**; pytest network/MariaDB attempts: **0**. The skipped tests are the opt-in live MariaDB cases. |
| Focused security tests | **56 passed in 9.15s** across production boundary, auth/RBAC, confirmation/replay, scope and release integration |
| Django API tests | **19 passed in 5.141s**; system check clean |
| Django deployment check | Synthetic safe production configuration: no errors, two warnings (`security.W005` HSTS subdomains and `security.W021` preload). These remain disabled pending institution-approved domain coverage. |
| Migration consistency | `manage.py makemigrations --check --dry-run`: no changes detected |
| Live MariaDB | Not run. The local wrapper could not bind loopback port 3307 (`Operation not permitted`); only the process launched by this attempt was stopped. No remote ERP connection was attempted. |
| Local Gemma inference | Not run in this pass; the expected pinned snapshot is not present at the standard local Hugging Face cache path. Historical cached-model evidence is in [RELEASE_VALIDATION.md](RELEASE_VALIDATION.md). |
| RAG / browser / physical voice | Automated suite passed, including browser voice lifecycle coverage. No live browser session or physical microphone/speaker acceptance was performed. Physical voice acceptance is **PENDING MANUAL TEST**. |

## Security corrections in this pass

The independent review identified weak-password acceptance and missing production HTTPS enforcement. Current settings now enable Django's standard password validators, and the local demo account helper applies them before account creation. Production settings fail fast for `DEBUG=True`, missing/unsafe secrets, wildcard/loopback hosts, disabled HTTPS/HSTS, or real writes. HTTPS redirection, secure session/CSRF cookies and one-year HSTS are enabled in production. Reverse-proxy SSL-header trust is opt-in and must only be enabled for a controlled proxy that overwrites client-supplied headers. HSTS subdomains/preload remain off unless approved. Focused regression tests passed.

Ordinary pytest and Django management tests set `VOXERP_DISABLE_GEMMA=True` to avoid loading the large local inference model during test collection; this does not change production inference. Local MariaDB preflight ignores empty files only in the standard MariaDB system schemas and continues to reject empty ERP-schema table files.

## Acceptance summary

- Student authentication/session/CSRF and self-only authorization: current automated tests passed.
- Marks, attendance, timetable, cross-student denial and live ERP source-of-truth: historical isolated-dump validation; current live database access blocked in this environment.
- Teacher/HOD/Admin permissions: architecture remains fail-closed pending authoritative institutional identity/scope grants.
- Gemma intent/entity/course-code normalization: historical local inference and regression evidence; actual inference not repeated in this pass.
- RAG policy retrieval/isolation: automated regression suite passed; real ERP/policy deployment acceptance remains environment-specific.
- Speech pipeline: browser lifecycle coverage exists; no physical microphone or speaker acceptance is claimed.
- SQL parameterization, confirmation, reauthorization and replay safety: current automated security tests passed; no real writes were enabled.
- Production configuration: focused settings/password tests passed. `check --deploy` warnings and actual domain, proxy, secrets, hosting and ERP route remain infrastructure-dependent.
- Git release: no release merge, tag or push prepared in this pass; see handoff requirements and current checkout status in the execution report.

**Production: NOT READY. Demo: SUPERVISED READ-ONLY READY only when the authorized local clone is runnable. Writes: DISABLED.**
