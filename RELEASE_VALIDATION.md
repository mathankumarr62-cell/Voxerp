# Final working-model validation — 2026-09-21

The local student working model is usable with Django, cached local MLX Gemma, and the authorized real MariaDB dump. This is **not a claim that every role, remote deployment, or physical voice requirement is complete**. The external dependencies below remain explicit.

## Completion matrix

| Component | DONE | EXTERNAL BLOCKER | NOT DONE | Evidence |
|-----------|------|------------------|----------|----------|
| Django startup/check/migrations | Yes | — | — | Check clean; both existing and separate demo application DB migrations current |
| Reproducible real ERP clone | Yes | — | — | 298 tables restored; loopback 3307; persistent stop/start; documented helper |
| Login and trusted identity | Yes | — | — | Browser password login as 917 and 44; local nonstaff users; username → ERP ID |
| Local Gemma | Yes | — | — | MLX model loaded; six model-classified read/policy/security queries plus deterministic write safety parser |
| Marks | Yes | — | — | 917/IT25201: IAT1 62/100, IAT2 77/100; real browser response |
| Attendance | Yes | — | — | 917/IT25201: 106 hourly rows; real browser response |
| Department-scoped timetable | Yes | — | — | 44: 40 periods; browser query and adapter/service validator |
| Timetable data for student 917 | — | Yes | — | No department 2/year 2/semester 3/section A allocations in supplied dump |
| Policy RAG | Yes | — | — | Browser receives local authorization/attendance policy text; no ERP access grant |
| Student/cross-student RBAC | Yes | — | — | Own reads work; 918 and ambiguous target denied as 917 |
| Teacher academic scope | — | Yes | — | Candidate enrollment/faculty relationships exist; account mapping and approved operation/term scope missing |
| HOD/Admin academic scope | — | Yes | — | No approved academic permission contract; explicit fail-closed roles including superusers |
| Confirmation and write safety | Yes | — | — | Confirm requires signed token; actual confirmation returns 403 disabled; replay 409; SELECT-only DB account |
| Production ERP writes | — | — | Intentionally disabled | No production/remote writes; VOXERP_ALLOW_REAL_WRITES=False |
| Browser text flow | Yes | — | — | Login, real inference, ERP/RAG, response, security checks; student logout regression fixed |
| Speech event wiring | Yes | — | — | Controlled transcript event reaches actual Django/Gemma/ERP response; explicitly not physical STT |
| Physical microphone | — | Yes | — | Native SpeechRecognition attempt returned not-allowed in automated Chrome |
| TTS browser lifecycle | Yes | — | — | 199 voices; actual utterance start and end events |
| Audible speaker acceptance | — | Yes | — | Agent cannot attest physical audibility; exact Mac manual procedure in DEPLOYMENT.md |
| Remote ERP/Tailscale | — | Yes | — | Tailscale stopped; 100.126.94.44:3306 timed out after five seconds outside sandbox |
| Automated suites | Yes | — | — | Results below; offline pytest recorded zero network/MariaDB attempts |
| Security review | Yes | — | — | Tests and live browser checks below; limited to reviewed code/local environment |
| Documentation/reproducibility | Yes | — | — | Deployment, schema evidence, pinned environment/model and safe account helper |
| Local release commit | Yes | — | — | 22 intentional files; clean tracked/untracked status; private artifacts ignored |
| GitHub branch publication | — | Yes | — | Push reached origin but GitHub rejected credentials: Invalid username or token |

## Exact automated results

- `.venv/bin/python -m pytest -q`: **115 passed, 26 skipped in 11.00s**; **Network/MariaDB attempts: 0**. The 26 skips are opt-in real database cases.
- `.venv/bin/python manage.py test api.tests`: **18 tests passed in 5.366s**; system check no issues. Management test mode explicitly disables real ERP access before `.env` loads.
- `.venv/bin/python -m unittest tests.test_person_b tests.test_person_b_additional`, with real access/writes disabled: **52 passed in 0.019s**.
- Local wrapper + `python -m unittest tests.test_db_adapter_mariadb`: **26 passed in 0.046s**, with a SELECT-only account and real writes disabled.
- `python manage.py check`: **no issues (0 silenced)**.
- `python manage.py migrate --check`: **exit 0**, existing Django DB. Demo wrapper migration readiness also checked separately.
- `python -m pip check`: **No broken requirements found**.
- `git diff --check`: clean during final review.

Failures investigated and resolved: recovery tests unintentionally loaded MLX under the sandbox (now use the existing injected test client); management tests inherited remote `.env` (now isolate test flags); the dump's final foreign-key constraints encountered historical orphan rows (session-only import checks disabled, original dump preserved); live initialization test expected writes despite the disabled guard (now asserts disabled); timetable omitted department (narrow adapter correction with regression coverage); student logout led to admin template (now returns to student login). Model-card metadata absent from the cache is excluded from offline runtime snapshot resolution; all eight required runtime files were already present. MLX emits a nonfatal audio mel-filter warning during initialization.

## Database evidence

Authorized input: `/Users/vijayaguru/Downloads/ramco_academic_system (33).sql`. Original dump not modified or committed. Two partial restore directories were preserved locally during diagnosis. The successful clone remains `.local-demo/`.

| Dataset | Rows |
|---|---:|
| Students | 2,763 |
| Courses | 965 |
| Enrollments | 35,742 |
| Daily attendance | 248,032 |
| Hourly attendance | 1,392,751 |
| Consolidated marks | 3,380 |
| Period allocations | 265 |
| Lab timetable | 1 |

The explicit read validator passed TCP, authentication/database selection, marks, subject attendance, timetable, both historical IAT expectations, service/RBAC/adapter comparison for all three reads, and cross-student rejection. Its inference is injected and labeled as such; actual Gemma evidence is below. Inputs: student 917/course IT25201 and separately approved timetable student 44. No lab-timetable integration is claimed.

`@@bind_address=127.0.0.1`, `@@port=3307`, `@@read_only=ON`, and normal-session `@@foreign_key_checks=1`. OS listener inspection showed only `127.0.0.1:3307`. Application grants contain SELECT on the ERP schema only (plus USAGE); no mutation privileges. Local root uses OS-user Unix-socket authentication; passwordless TCP root failed with error 1045. College/remote firewall exposure was not audited.

The old timetable query selected 15 rows from departments 1/7/9 for department-2 student 917. The six-line adapter correction adds department to the student metadata, allocation predicate and course lookup. It does not rewrite Person A's marks, attendance or mutation logic. The corrected query returns no_data for 917 and 40 periods for 44. No student or timetable records were changed.

## Gemma and browser evidence

Model: `mlx-community/gemma-4-e4b-it-4bit`, cached revision `475b9088d29754a3379866cf5aeb6b41acd313c2`; MLX 0.32.2 / mlx-vlm 0.7.0 on Python 3.13. The demo launcher resolves this revision offline. No cloud fallback or SQLite academic data was used.

Standalone real inference classified marks (4.38s), attendance (3.46s), timetable (1.72s), policy (1.77s), explicit student 918 (3.38s), and ambiguous student (1.72s). These times are single observations, not benchmarks. The write request uses the existing deterministic safety parser (0.00s), preserving period 6, absent, IT25201. It is not mislabeled as a Gemma generation.

Chrome password-login/query results through actual Django/Gemma/ERP:

| Identity/query | Observed result |
|---|---|
| 917: Show my IT25201 marks | IAT1 62/100 and IAT2 77/100, plus real assessment rows |
| 917: Show my IT25201 attendance | Present attendance entries from 2026-04-22 |
| 917: Show my timetable | You have no recorded data for that request. |
| 917: What is the attendance policy? | Retrieved student authorization and attendance-policy text |
| 917: Show student 918 marks | You can only access your own data. |
| 917: Show the student's marks | You can only access your own data. |
| 917: Mark me absent for IT25201 period 6 | Signed confirmation required |
| Confirm Yes | Real database writes are disabled. |
| 44: Show my timetable | Timetable for 44: Monday Period 1 ...; 40 adapter rows |

Browser speech support was present. Native microphone attempt returned **not-allowed**, with the application's text fallback message. A separately labeled controlled recognition event inserted the attendance transcript and received the real ERP reply. Actual TTS had 199 voices and start/end events. Neither a controlled transcript nor TTS events prove physical microphone capture or audible speakers. Follow the Mac manual acceptance procedure in DEPLOYMENT.md.

The login/dashboard rendered successfully, with no reported JavaScript page errors. The optional favicon returned 404. Browser startup was retried after the model finished loading; no persistent load failure remained.

## Security evidence and limits

Automated coverage verifies authentication, body/header identity spoofing, self-only reads, explicit/unknown/ambiguous targets, teacher unknown-scope denial, undefined HOD/Admin denial, RAG policy isolation, signed and user-bound confirmations, five-minute expiry, tampering, cancellation, replay across sessions, reauthorization, disabled writes before ERP connection, private files, CSRF, and isolated transaction tests. The new timetable regression asserts department filtering and safe NULL-department handling.

Actual browser HTTP checks: write confirmation denied, **403**; consumed-token replay, **409**; forged token, **400**; missing CSRF, **403**; `/.env`, **404**. Requests never choose authenticated identity. The Django service authorizes before academic read/mutation calls; the adapter remains an internal data layer, not a standalone identity/authentication API. The SELECT-only database login adds an independent write barrier. Direct Python access by a trusted process is outside HTTP RBAC's trust boundary.

Tracked-file secret-pattern audit found no matches and no tracked SQL/database/ZIP/backup artifacts. Generated credentials, passwords and academic clone directories are ignored and private; none are included in the release commit. This is a scoped source/local-runtime audit, not a claim of a comprehensive penetration test or of remote infrastructure security.

## External dependencies and handoff

1. Physical voice: allow the real Mac browser/OS microphone and complete spoken-input plus audible-output acceptance.
2. Teacher: approve account → faculty primary-key mapping and course/term/student/operation scope. 35,641 enrollment rows join faculty primary key; none join the separate employee-ID field. A class label is insufficient.
3. HOD/Admin: supply authoritative assignments, department boundaries, and academic read/write operation permissions. Existing ERP permission tables alone do not define the VoxERP contract.
4. Remote: authorized owner must start/restore Tailscale and private MariaDB reachability before read-only remote validation can occur.
5. Student 917 timetable: provide authoritative current-class allocations or updated approved data; no semester or department is inferred to fill the gap.
6. Git publication: `git push -u origin fix/gemma-entity-recovery` reached GitHub outside the sandbox but failed with “Invalid username or token. Password authentication is not supported for Git operations.” Supply an authorized credential through the Git credential manager, then retry that exact non-force command. No remote change is claimed.

See DEPLOYMENT.md for exact fresh-install and daily startup commands, passwords entered locally, query sequence, voice test, troubleshooting, and read-only verification. The final commit hash and actual push result are reported in the execution handoff; use `git log -1` to identify the checked-out release. No force push, bulk staging, backup deletion, or production ERP writes are authorized by this report.


## Final local completion validation — 2026-09-22

Canonical checkout: `/Users/vijayaguru/Developer/Voxerp`. Initial branch `main`,
HEAD `5416f94b73b5f8239d2ad60450592248a0a958b5`, clean working tree. Cached
`origin/main` was `c4043a84bb504eaa95637c6ee78b6d99858a573d`; no fetch or push was
performed. The Desktop checkout's existing uncommitted work was left untouched.
Completion branch: `fix/verified-erp-completion`; implementation commit
`eb0cec07c28dec0a7f62ba159a166b771fd6b796`.

Already working: Django authentication/CSRF/session boundary, dynamic student
marks/course attendance/timetable, department-aware timetable filtering, signed
single-use confirmation with reauthorization, policy isolation, local Gemma and
browser text/speech wiring. Baseline was 214 passed, 26 live tests skipped,
zero network/MariaDB attempts.

Changes: explicit local-demo versus institutional identity boundary; current
ERP active/discontinued checks; overall daily attendance; duplicate-aware hourly
absence counts with conflicting-evidence denial; narrow absence-question entity
recovery after local inference; pinned default cached model loading; stricter
optional teacher batch/term/date/ambiguity checks; malformed-target/unsupported
operation denial; removal of fixed expected demo marks from live validation.
The real marks and timetable query implementations were preserved.

### Exact checks

| Check | Result |
| --- | --- |
| `.venv/bin/python -m pytest -q -p no:cacheprovider` | **268 passed, 26 skipped, 1 warning**, 13.46 seconds |
| Offline suite network/MariaDB attempts | **0**; global guards make any attempted access fail the session |
| Local-wrapper `python -m unittest tests.test_db_adapter_mariadb` | **26 tests, OK**, 0.070 seconds; writes disabled |
| `python manage.py check` | **No issues (0 silenced)** |
| `python manage.py migrate --check` | **Pass**, default auth DB and separate local-demo auth DB |
| `python manage.py makemigrations --check --dry-run` | **No changes detected** |
| `python -m compileall -q api config core intelligence rag voice scripts tests db_adapter.py` | **Pass**; changed/new files compiled again after final edit |
| `git diff --check` | **Pass** |
| Actual Gemma + authenticated Django + real SQL | **Pass**, four distinct students |
| Chrome login, query submission, rendered marks, browser error check | **Pass**; no reported browser errors |

The warning comes from Transformers audio mel-filter configuration; no stack
versions were changed. Focused API, identity, scope, revocation, confirmation,
policy isolation, voice lifecycle, Gemma recovery and security regressions are
included in the full offline run. The 26 skipped cases were then run separately
against the isolated clone, not silently counted as offline passes.

Reproduce actual local inference and SQL validation with:

```bash
.venv/bin/python scripts/validate_completion.py
```

This script uses the existing local wrapper's loopback-only configuration,
asserts server read-only mode and SELECT grants, and creates a disposable SQLite
authentication database. It performs actual Django password login, CSRF/session
requests, actual local Gemma inference, and SQL-backed comparisons for students
1 and 2 (selected dynamically from populated active rows), 44 and 917. It checks
marks against underlying consolidated CSV assessment fields, course-name/code
attendance, overall daily attendance, hourly row identities and absence responses,
exact-class timetable availability, unknown-course no-data, forged body identity,
cross-student denial, and CSRF rejection. Changing the logged-in student changes
the resulting academic answer. No expected academic score is hardcoded. This
validator passed again after duplicate-aware hourly counting was added.

Browser verification used installed agent-browser 0.27.0 and Google Chrome,
a loopback server on port 8011, temporary demo credentials and a temporary auth
DB. Login, dashboard controls, actual IT25201 marks query and result rendering
were observed; the TTS UI entered playback state. This does **not** establish
physical microphone capture or audible speaker output. The temporary browser,
server and authentication state were cleaned up; the existing ERP server was
left intact. Screenshots containing local academic data were not committed.

Runtime: Python **3.13.12**, MLX **0.32.2**, mlx-vlm **0.7.0**, Django **5.2.17**;
model `mlx-community/gemma-4-e4b-it-4bit`, revision
`475b9088d29754a3379866cf5aeb6b41acd313c2`. Cached local inference was actually
used; no cloud fallback or model/dependency replacement was introduced.

Safety: `VOXERP_ALLOW_REAL_WRITES=False`; MariaDB listens on **127.0.0.1:3307**,
server read-only mode is ON and the application account has SELECT only. Live
validation intentionally accessed only this local ERP instance. Ordinary pytest
made zero network/MariaDB attempts. No production DB, original SQL dump, private
credentials or unrelated checkout was modified; no deployment or push occurred.

### Remaining evidence boundaries

The dump has 298 tables but zero authentication users/groups/student-login rows.
Faculty employee and assignment joins are proven; institutional account binding,
semantic role assignment, current HOD appointments and operation grants are not.
Teacher/HOD/Admin academic access therefore remains disabled in the application.
Passing synthetic scope-source tests does not establish those roles in the ERP.
`AuthenticatedIdentityResolver` is the institutional integration point; production
rejects the numeric-username demo convention. See SCHEMA_MAPPING.md for observed
counts/relationships and the enabled operation matrix, and
INSTITUTIONAL_AUTH_REQUIREMENTS.md for the missing owner-supplied contract.
Physical microphone/speaker acceptance and production integration remain unverified.

Documentation updated: README.md, DEPLOYMENT.md, SCHEMA_MAPPING.md,
INSTITUTIONAL_AUTH_REQUIREMENTS.md, RELEASE_VALIDATION.md and `.env.example`.
