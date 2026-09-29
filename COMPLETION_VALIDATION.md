# VoxERP current validation

**2026-09-28 follow-up against `fix/gemma-entity-recovery`, base commit
`c83cf94a061ff14af1b71f3309d3a5f7cac0933e`, plus the uncommitted changes described below.**
This section supersedes earlier same-day results. No release is approved while
physical voice acceptance remains pending.

## Current evidence

| Gate | Result |
| --- | --- |
| Ordinary regression | **207 passed, 26 skipped in 10.19s**, network/MariaDB attempts **0**. The skips are the separately run live tests. Plain pytest now starts without needing a development environment exported first. |
| Focused security and acceptance regressions | **110 passed in 9.27s**, zero network/MariaDB attempts. Covers authentication, CSRF, self/cross-student access, privileged scope and revocation, authorization before ERP/schema access, policy isolation, confirmation reauthorization/replay, write guards, production defaults and error redaction. |
| Django API tests | **19 passed in 4.868s**; system check clean. |
| Django check / migrations / compilation | Passed; no migration changes. Commands use explicit development mode, real database disabled and Gemma disabled. |
| Live MariaDB suite | **26/26 passed**, final repeat in 0.053s (initial successful run 23.625s) through `scripts/local_demo.py run -- .venv/bin/python -m unittest tests.test_db_adapter_mariadb`. Initial sandbox attempt failed (13 failures, 4 errors); authorized host execution resolved the loopback restriction. |
| Local database safety / integrity | Passed: loopback-only bind, read-only server, SELECT-only demo grants, local infile disabled, no empty application table files, **298 tables checked with CHECK TABLE QUICK and no reported errors**. `VOXERP_ALLOW_REAL_WRITES=False`. |
| Real ERP read validator | Passed marks, attendance, timetable, historical score assertions, service/adapter agreement and cross-student denial for documented test inputs. This validator explicitly stubs inference. |
| Actual pinned Gemma | **9/9 passed**, actual MLX inference with revision `475b9088d29754a3379866cf5aeb6b41acd313c2`, offline flags enabled, no injected cloud client. Cases: marks, attendance, timetable, course name, course code, separated spoken code, conversational academic request, policy and explicit other-student target. |
| Voice software | Generic normalization and service-to-response/TTS preparation regressions pass; existing controlled browser speech lifecycle test passes. These are not physical audio evidence. |
| Browser | Actual local login page rendered, screenshot inspected, browser error command reported no errors. Browser STT/TTS APIs available in secure context. Physical audio remains unverified. |
| Physical voice | **BLOCKED for cases 1–8**: available tools cannot provide physical microphone utterances or confirm audible speaker output. Browser exposes STT/TTS APIs in a secure context; that is not physical evidence. No physical PASS claimed. |
| Production safety | Synthetic production `check --deploy` passed with only W005/W021 (HSTS subdomains/preload), awaiting approved domain coverage. Real writes remain disabled. Actual institutional deployment is not validated. |
| Repository hygiene | No tracked `.env`, SQL dump, database, `.local-demo` data or archive. Credential-pattern review found only test passwords. Ignored private artifacts preserved. `git diff --check` passed. |
| Release | No commit, merge, final tag or push. Protected baseline and RC tag objects unchanged. |

## Changes and bounded security review

Reviewed settings, RBAC, scope, service, HTTP views, adapter, intent engine, RAG,
STT and TTS. Two concrete medium-severity findings were fixed:

- `api/services.py:109` (`_backend_guard`): missing/blank environment previously used
  development behavior while Django defaulted to production. The service now
  defaults to production, normalizes whitespace and rejects unknown environments.
- `api/views.py:73` and `api/views.py:104` (query/confirm handlers): broad `ValueError` handlers returned internal
  exception messages to clients. Only controlled `InvalidRequest` messages are
  now returned; internal errors receive generic responses. Both endpoints have
  regression coverage.

Also restored subject-free attendance reads through the existing adapter;
added bounded generic spoken-course normalization before classification and
RBAC; and added explicit pytest settings so pytest-django cannot initialize
production settings before test isolation. Production defaults were not weakened.
No ERP schema or institutional authorization mappings were invented or changed.

The pinned model has no ERP tools and cannot authorize writes. Authentication
supplies identity; deterministic RBAC and signed, one-use, reauthorized
confirmations remain in place. No real attendance confirmation was executed.
The review found no additional concrete unresolved vulnerability in the reviewed
paths; this is a bounded code review, not institutional security approval.

## Repository audit

The initial working tree was clean. Local branch was three commits ahead of its
tracking ref; local main was eleven behind its tracking ref. Read-only remote
inspection confirmed origin hardened branch at `148efbe` and main at `90f4c03`.
The baseline tag object is `fe12d6893c9f49595d60f0827354262ff7f3ec1c` locally and
remotely. The local RC tag object is
`d28ef7dbb7f4a8173a451340ddff0fea72afdbf6`; no matching RC ref was returned by origin.
The other registered worktree `/private/tmp/voxerp-completion` was already
prunable; it was not removed or used. Both tag diffs were reviewed before edits.

## Remaining acceptance and institutional boundaries

Physical microphone/STT and audible speaker acceptance remains blocked for all
eight cases because no physical audio input/output verification tool is available. Cross-student case `Show student 917 marks` requires an authenticated
account other than 917. Genuine missing course/timetable data must be reported,
never synthesized. Do not confirm the period-1 attendance request.

Institutional authentication, authoritative identity/role mappings, Teacher/HOD/
Admin grants, operation permissions, revocation and academic-term rules, official
policies, production connectivity/read-only credentials, approved hosting,
HTTPS/domain, secrets/rotation, monitoring and security/operational/deployment
approvals remain outstanding; see `INSTITUTIONAL_HANDOFF.md`. Keep
`VOXERP_ALLOW_REAL_WRITES=False`. No main promotion, final tag or push is allowed
until all technical acceptance gates pass.

## Earlier same-day validation (historical)

The following record is retained for provenance only and is superseded above.

### Earlier report

**Current validation pass: 2026-09-28.** This report distinguishes checks run against the current checkout from historical acceptance evidence. A previous result is not treated as a present run.

## Current checkout evidence

| Check | Current result |
| --- | --- |
| Checkout | `/Users/vijayaguru/Desktop/Voxerp`, branch `fix/gemma-entity-recovery`; protected baseline and RC tags unchanged |
| Django system check | `manage.py check`: passed after security settings changes |
| Migration consistency | `manage.py makemigrations --check --dry-run`: no changes detected |
| Changed-area regressions | Passed, including production security/password checks, local-demo guard, service lifecycle, verified teacher/HOD/Admin scope and authorization-boundary regressions |
| Python compilation | `compileall -q api intelligence rag tests scripts manage.py conftest.py`: passed |
| Worktree formatting | `git diff --check`: passed |
| Full pytest suite after security fixes | **189 passed, 26 skipped in 10.45s**; pytest network/MariaDB attempts: **0**. The skipped tests are the opt-in live MariaDB cases. |
| Focused security tests | **59 passed in 1.92s** across production boundary, auth/RBAC, confirmation/replay, scope and release integration |
| Django API tests | **19 passed in 5.544s**; system check clean |
| Django deployment check | Synthetic safe production configuration: no errors, two warnings (`security.W005` HSTS subdomains and `security.W021` preload). These remain disabled pending institution-approved domain coverage. |
| Migration consistency | `manage.py makemigrations --check --dry-run`: no changes detected after security integration |
| Live MariaDB | Not run. The local wrapper could not bind loopback port 3307 (`Operation not permitted`); only the process launched by this attempt was stopped. No remote ERP connection was attempted. |
| Local Gemma inference | Not run in this pass; the expected pinned snapshot is not present at the standard local Hugging Face cache path. Historical cached-model evidence is in [RELEASE_VALIDATION.md](RELEASE_VALIDATION.md). |
| RAG / browser / physical voice | Automated suite passed, including browser voice lifecycle coverage. No live browser session or physical microphone/speaker acceptance was performed. Physical voice acceptance is **PENDING MANUAL TEST**. |

## Security corrections in this pass

The independent review identified weak-password acceptance, missing production HTTPS enforcement, and development-mode fallback if `VOXERP_ENV` was omitted or misspelled. Current settings enable Django's standard password validators, and the local demo account helper applies them before account creation. `VOXERP_ENV` now defaults fail-closed to production, accepts only explicit `development` or `production`, and rejects unknown labels. Production settings fail fast for `DEBUG=True`, missing/unsafe secrets, wildcard/loopback hosts, disabled HTTPS/HSTS, or real writes. HTTPS redirection, secure session/CSRF cookies and one-year HSTS are enabled in production. Reverse-proxy SSL-header trust is opt-in and must only be enabled for a controlled proxy that overwrites client-supplied headers. HSTS subdomains/preload remain off unless approved. Focused regression tests passed. Upstream authorization hardening also removed name-based student resolution and ERP schema discovery before authorization, validates scope evidence strictly, requires teacher section scope, and fails closed on unavailable/malformed evidence.

Ordinary pytest and Django management tests set `VOXERP_DISABLE_GEMMA=True` to avoid loading the large local inference model during test collection; this does not change production inference. Local MariaDB preflight ignores empty files only in the standard MariaDB system schemas and continues to reject empty ERP-schema table files.

## Acceptance summary

- Student authentication/session/CSRF and self-only authorization: current automated tests passed, including malformed-filter and no-name-lookup regressions.
- Marks, attendance, timetable, cross-student denial and live ERP source-of-truth: historical isolated-dump validation; current live database access blocked in this environment.
- Teacher/HOD/Admin permissions: architecture remains fail-closed pending authoritative institutional identity/scope grants.
- Gemma intent/entity/course-code normalization: historical local inference and regression evidence; actual inference not repeated in this pass.
- RAG policy retrieval/isolation: automated regression suite passed; real ERP/policy deployment acceptance remains environment-specific.
- Speech pipeline: browser lifecycle coverage exists; no physical microphone or speaker acceptance is claimed.
- SQL parameterization, confirmation, reauthorization and replay safety: current automated security tests passed; no real writes were enabled.
- Production configuration: focused settings/password tests passed. A synthetic safe production configuration passed with two expected `check --deploy` warnings (`security.W005` HSTS subdomains and `security.W021` preload); actual domain, proxy, secrets, hosting and ERP route remain infrastructure-dependent.
- Git release: no release merge, tag or push prepared in this pass; see handoff requirements and current checkout status in the execution report.

**Production: NOT READY. Demo: SUPERVISED READ-ONLY READY only when the authorized local clone is runnable. Writes: DISABLED.**

## Physical acceptance ledger (current follow-up)

All inputs below were requested for physical testing. No actual microphone
transcript, displayed voice response or heard audio is recorded: tools cannot
provide a physical utterance or verify sound at the speaker. Software checks
must not be substituted for these observations.

| Case | Requested utterance | Physical transcript / intent / authorization / route / display / TTS / audible output |
| --- | --- | --- |
| 1 | What is my attendance? | Blocked / not observed through physical speech |
| 2 | What are my AD3491 marks? | Blocked / not observed through physical speech |
| 3 | Show my timetable. | Blocked / not observed through physical speech |
| 4 | What is the attendance policy? | Blocked / not observed through physical speech |
| 5 | Show student 917 marks. | Blocked / not observed through physical speech |
| 6 | Mark me absent in AD3491. | Blocked / not observed through physical speech |
| 7 | Mark me absent in AD3491, period 1. | Blocked / not observed through physical speech; never confirmed |
| 8 | A D three four nine one marks. | Blocked / not observed through physical speech |

No physical test submitted an ERP write. The server/read account/app write
barriers remained in force throughout validation. Approval to proceed
without a human report does not supply evidence of audible output.

## Actual model plus live ERP software acceptance

A separate current run used an existing active nonstaff, nonsuperuser demo
account other than 917, resolved through the application's `_identity` mapping.
It used actual pinned Gemma, the real read-only ERP and TTS text preparation.
Inputs were typed strings, not microphone transcripts; responses were inspected
in memory and private academic values were not printed. No browser display or
audible output is claimed by this service-level run.

| Case | Intent | Authorization / route | Observed software outcome |
| --- | --- | --- | --- |
| 1 | read attendance | allowed / SQL | Nonempty response; TTS text prepared |
| 2 | read marks | allowed / SQL | Nonempty response; TTS text prepared; this alone does not assert populated AD3491 marks |
| 3 | read timetable | allowed / SQL | Nonempty response; TTS text prepared |
| 4 | policy_query policy | allowed / RAG | Nonempty policy response; TTS text prepared |
| 5 | read marks | denied | Cross-student request blocked |
| 6 | write attendance | allowed / clarification | Valid period requested; no confirmation or adapter write |
| 7 | write attendance | allowed / pending | Confirmation payload produced; never confirmed; no adapter write |
| 8 | read marks | denied as ambiguous target | Generic normalization to AD3491 verified; bare phrase has no explicit self-reference |

Every case asserted that `mark_attendance` was not called. The injected guard
only prohibited mutation; model inference and all academic reads were real.
