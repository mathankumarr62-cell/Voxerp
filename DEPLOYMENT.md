# Reproducible local demo

Django is the active web/API runtime. Academic data comes from the authorized real MariaDB dump. SQLite is used only for Django users, sessions, and confirmation replay records. No Flask, cloud model substitution, fabricated ERP records, or college ERP writes are involved.

## Prerequisites and Python

Validated host: Apple Silicon macOS, Python 3.13, Homebrew MariaDB 12.3.3, MLX 0.32.2, mlx-vlm 0.7.0, Django 5.2.17. `mariadb`, `mariadbd`, and `mariadb-install-db` must be on PATH. Use a compatible Apple Silicon host with enough memory for the model. Chrome is needed for the supported browser speech test.

From the repository root, use the existing `.venv`, or provision one:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-demo-lock.txt
python -m pip check
```

The lock file records installed versions on the validated host; a fresh download/install still requires package-network availability. It excludes the retired Flask runtime. `requirements.txt` remains the base install and `requirements-gemma.txt` the optional model stack.

Provision the exact model snapshot once (network required only when uncached):

```bash
python -c 'from huggingface_hub import snapshot_download; print(snapshot_download("mlx-community/gemma-4-e4b-it-4bit", revision="475b9088d29754a3379866cf5aeb6b41acd313c2"))'
export VOXERP_GEMMA_MODEL="$HOME/.cache/huggingface/hub/models--mlx-community--gemma-4-e4b-it-4bit/snapshots/475b9088d29754a3379866cf5aeb6b41acd313c2"
```

The demo wrapper resolves this exact cached revision automatically unless `VOXERP_GEMMA_MODEL` is explicitly set. If a custom model is intended, export its local path. The demo wrapper sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`: a missing model fails closed rather than downloading at demo time. No normal-path cloud API key is needed. The deterministic attendance-write parser remains an existing safety guard; those commands do not invoke Gemma classification.

## Authorized ERP clone: first setup only

Keep the original authorized SQL file outside Git. Never edit it. On this Mac:

```bash
python scripts/local_demo.py init --dump '/Users/vijayaguru/Downloads/ramco_academic_system (33).sql'
```

Other team members must use their own authorized copy/path. The helper creates `.local-demo/` with mode 0700, a separate MariaDB data directory, and private generated credentials. It refuses to overwrite existing state. MariaDB binds **127.0.0.1:3307 only**, enables server read-only mode, disables binary logging and local-file import, and grants the application user **SELECT only** on `ramco_academic_system`. It does not alter the system MariaDB service or remote ERP.

The historical dump contains orphan rows: importing its final foreign-key statements with checks enabled fails with ERROR 1452. The helper uses `FOREIGN_KEY_CHECKS=0` only in the import connection so it preserves the unchanged dump and its original rows. Normal application connections have foreign-key checks enabled. The successful restore contains 298 tables. Do not use `--force`, fabricate missing parents, or change the source dump.

`.local-demo/environment.json` contains a random database password and Django secret (mode 0600). `run` loads these into the child process without printing them, overriding a remote `.env`. It forces `VOXERP_USE_REAL_DB=True`, `VOXERP_ALLOW_REAL_WRITES=False`, `VOXERP_INITIALIZE_DATABASE=False`, `VOXERP_OFFLINE_MODE=False`, development mode, local allowed hosts, and `DEBUG=True` for localhost HTTP cookies. Django uses `.local-demo/auth.sqlite3`; existing local application accounts remain untouched.

Treat the entire clone and any restore logs as private academic data. All `.local-demo*` directories, SQL dumps, database files, ZIPs and existing backups are ignored, not deleted. The local MariaDB administrator requires the current Mac user’s Unix-socket identity; passwordless TCP root is rejected. It is for restoring this private clone only. Do not publish, upload, or expose its socket/data directory.

## Migrate and provision local login

```bash
python scripts/local_demo.py run -- python manage.py migrate
python scripts/local_demo.py run -- python scripts/create_demo_user.py --student-id 917
python scripts/local_demo.py run -- python scripts/create_demo_user.py --student-id 44
```

The account helper verifies the exact numeric ERP student ID by a read, then asks for a password twice without echo. It creates nonstaff, nonsuperuser accounts only in the local Django database. Existing accounts are left unchanged. Passwords are never included in Git or documentation. To choose/reset an existing local demo password:

```bash
python scripts/local_demo.py run -- python manage.py changepassword 917
python scripts/local_demo.py run -- python manage.py changepassword 44
```

Usernames map directly to ERP student IDs. Names, registration numbers, request bodies, and HTTP headers cannot establish or override identity. Never use `createsuperuser` as the student demo account. Admin/HOD groups and superusers have no defined academic permissions; teacher/staff academic access also fails closed pending approved scope.

## Every demo

```bash
source .venv/bin/activate
python scripts/local_demo.py start
python scripts/local_demo.py run -- python manage.py runserver 127.0.0.1:8000 --noreload
```

Open **http://127.0.0.1:8000/** and log in. `--noreload` avoids loading the model twice. Stop Django with Ctrl-C. Stop only this local database when finished:

```bash
python scripts/local_demo.py stop
```

The dataset survives stop/start. Do not run a public HTTP server over the repository.

## Demonstration sequence

As `917`:

1. `Show my IT25201 marks` — IAT1 62/100, IAT2 77/100.
2. `Show my IT25201 attendance` — actual hourly attendance summary.
3. `Show my timetable` — safe no-data response: the dump lacks department 2/year 2/semester 3/section A allocations.
4. `What is the attendance policy?` — repository policy RAG, not student records or an asserted college attendance-percentage rule.
5. `Show student 918 marks` — denied.
6. `Show the student's marks` — denied/ambiguous; never another student's results.
7. `Mark me absent for IT25201 period 6` — confirmation only. Choosing Yes returns `Real database writes are disabled.`; no ERP modification occurs. A consumed token cannot be replayed.
8. Log out, log in as `44`, and ask `Show my timetable` — exact department/class schedule. Never use client fields to switch identity.

A successful read cannot guarantee a record exists. Do not advertise student 917's missing timetable as working data. The adapter now includes department in allocation and course resolution, correcting a proven cross-department data leak.

## Physical microphone and TTS: manual acceptance on the Mac

1. Open the local URL in Chrome on the Mac with a working microphone and speakers.
2. Allow microphone access in macOS System Settings → Privacy & Security → Microphone and in Chrome's site settings. Use localhost or HTTPS.
3. Log in as `917`, click **Use microphone**, and speak **Show my IT25201 attendance**.
4. Verify the actual recognized words appear in the text box, the attendance response appears, and the response is audibly spoken.
5. Repeat `Show my timetable` as account `44`. Do not voice-test an ERP write.
6. Record browser/version, permission status, transcript, returned answer, and audible playback. A synthetic speech event verifies wiring only; it does not pass this test.

Speech recognition depends on browser support, permission, microphone hardware and potentially the browser vendor's recognition service/network. Text remains usable when speech fails. TTS event delivery does not independently prove sound reached the speaker. See the release report for the actual automated environment result.

## Validation

Normal pytest blocks all network/MariaDB attempts and skips the 26 explicit live cases:

```bash
python -m pytest -q
python manage.py check
python manage.py migrate --check
python manage.py test api.tests
VOXERP_USE_REAL_DB=False VOXERP_ALLOW_REAL_WRITES=False python -m unittest tests.test_person_b tests.test_person_b_additional
```

`manage.py test` explicitly disables real ERP access before reading `.env`. Run local-demo migration readiness and real READ validation separately:

```bash
python scripts/local_demo.py run -- python manage.py migrate --check
python scripts/local_demo.py run -- python scripts/validate_real_reads.py --student-id 917 --subject IT25201 --timetable-student-id 44
python scripts/local_demo.py run -- python -m unittest tests.test_db_adapter_mariadb
```

The read validator explicitly reports stubbed inference. Actual Gemma/browser evidence is separate. The live suite keeps write safety disabled, including the initialization guard. Never run manual transaction probes against college/production ERP.

## Remote deployment and remaining authorization

Remote ERP is configured privately at `100.126.94.44:3306`. On this validation host Tailscale was stopped and a five-second TCP probe timed out. An authorized network owner must restore Tailscale/peer/listener availability. No remote authentication or read success is claimed. Never expose 3306 publicly or change credentials to diagnose a failed TCP connection.

For deployment use Django WSGI/ASGI behind HTTPS, `VOXERP_ENV=production`, `DEBUG=False`, an explicit random secret and allowed hosts, trusted account provisioning, real private ERP credentials, and `VOXERP_ALLOW_REAL_WRITES=False`. The local demo wrapper is deliberately development-only. See SCHEMA_MAPPING.md for the missing teacher/HOD/Admin authorization contract.

## Troubleshooting

- **Existing `.local-demo`:** use `start`; initialization intentionally refuses overwrite. If initialization stopped before creating the ERP database, start it and use `restore --dump PATH`. If a partial ERP database exists, preserve the failed directory and diagnose its private logs before creating a fresh clone; there is no automatic deletion/reset.
- **Port 3307 busy:** stop the identified conflicting local service or use an isolated host; do not expose MariaDB on another network interface.
- **Import failure:** inspect `.local-demo/restore-error.log` locally. It may contain academic SQL; never attach it to public issues.
- **Missing Gemma / Metal failure:** run on the validated Apple Silicon host with OS/GPU access, check the cached snapshot and pinned dependencies. No cloud fallback is enabled.
- **Login redirects or CSRF failure:** use the same localhost host consistently and the wrapper's development settings. Production requires HTTPS secure cookies.
- **No timetable for 917:** expected dataset gap, not grounds to return another department's schedule.
- **Teacher/HOD/Admin denied:** expected until authoritative identity, term/course scope, and operation permissions are approved.
- **Voice fails:** complete the manual hardware/browser permission checks; retain text input.
