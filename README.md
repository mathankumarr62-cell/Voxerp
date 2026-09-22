# VoxERP

VoxERP is a Django-based, voice-enabled academic ERP assistant. It answers only supported academic-data and policy questions; it is not a general chatbot.

## Architecture

`Django` owns login, sessions, CSRF protection, the web UI, and the JSON API. `IntentEngine` uses local Gemma to produce validated intent JSON. Deterministic `RBAC` authorizes that intent before the `DataRouter` selects either SQL or policy RAG. `db_adapter.py` is the only ERP integration layer and reads the existing MariaDB ERP schema. Policy documents in `rag/policy_documents/` are retrieval-only and can never grant access. Browser speech APIs provide optional STT/TTS; text input always remains available.

Django's local SQLite database (`voxerp_app.sqlite3`) is for users, sessions, and consumed confirmation digests only. It is never used as the academic ERP database and Django migrations must never target the college MariaDB instance.

## Setup

Follow [DEPLOYMENT.md](DEPLOYMENT.md) for the tested Apple Silicon setup, authorized real-dump restore, local student login, startup, and voice test. The demo uses local Gemma and MariaDB, with real writes disabled and a SELECT-only ERP account. Do not use a superuser for the student demo.

For an already initialized checkout:

```bash
source .venv/bin/activate
python scripts/local_demo.py start
python scripts/local_demo.py run -- python manage.py runserver 127.0.0.1:8000 --noreload
```

Open `http://127.0.0.1:8000/` and sign in with the locally provisioned account. Username `917` maps only to ERP student ID `917`. Ask “Show my IT25201 marks”, “Show my IT25201 attendance”, or “What is the attendance policy?”. Student `917` has no matching current timetable in the supplied dump; student `44` has a department-scoped timetable and must log in separately to view it. Missing data is never filled with another department's schedule.

Teacher academic access remains blocked pending a verified teacher identity/scope contract. HOD/Admin groups and superusers are explicitly denied academic permissions. See [RELEASE_VALIDATION.md](RELEASE_VALIDATION.md) for current evidence and blockers.

## Configuration and ERP safety

Copy `.env.example`; it contains placeholders only. Configure `DJANGO_SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and the `DB_*` values outside version control.

`VOXERP_USE_REAL_DB=True` enables adapter reads from the private MariaDB ERP. `VOXERP_ALLOW_REAL_WRITES` must remain `False` during development and testing. `VOXERP_ENV=production` rejects academic fixture mode. Offline mode combined with real DB access is rejected, never silently redirected to demo data. For isolated local fixtures explicitly keep real DB access disabled. Never expose MariaDB port 3306 publicly.

Gemma is local and configured with `VOXERP_GEMMA_MODEL`, `VOXERP_GEMMA_MAX_TOKENS`, `VOXERP_GEMMA_TEMPERATURE`, and `VOXERP_GEMMA_REPETITION_PENALTY`. If MLX/Gemma is unavailable, intent parsing fails closed; no cloud model or API key is required for the normal path.

## API

All API calls require a Django session and CSRF token.

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Authenticated assistant dashboard |
| `GET /users` | Authenticated current-user compatibility identity |
| `POST /api/query/` | Submit `{ "text": "..." }` |
| `POST /api/confirm/` | Submit `{ "confirm": "yes|no", "pending": "signed-token" }` |

Write requests first return a signed confirmation token. Tokens expire after five minutes, are bound to the authenticated user, are consumed once, and are reauthorized immediately before a write. A “no” response never writes.

## Security rules

- Client-supplied roles and user IDs are never used by Django authorization.
- Students can access only their own marks, attendance, and timetable.
- Explicit other or unknown students are denied; ambiguous targets fail closed.
- Teachers fail closed unless their permitted scope can be verified.
- RAG explains policy only; it cannot expose records or grant authorization.
- Input is size-limited, JSON is validated, and model output is validated before use.
- Errors are logged server-side without returning stack traces, credentials, prompts, or tokens.

## Testing

```bash
python3 manage.py check
python3 manage.py test api.tests
python3 -m pytest -q -p no:cacheprovider
```

The Django API and security test suite is the active validation path. New deployments use Django via `manage.py`.

## Troubleshooting

- **Redirected to login:** create/sign in to a Django user first.
- **Voice unavailable:** grant browser microphone permission or use text input.
- **Gemma unavailable:** install the Apple Silicon MLX stack appropriate to the host and model, or expect requests to fail safely as unsupported.
- **Database unavailable:** verify private/Tailscale connectivity and `DB_*` values; never change write safety settings to diagnose a connection.

Flask is retired. The protected Person A adapter retains the real ERP read/write contracts. Run `python scripts/validate_real_reads.py --student-id <approved-id> --subject <course-code>` for explicit read-only MariaDB validation; inference is stubbed and reported separately. Never run the manual transaction probes as tests. See [DEPLOYMENT.md](DEPLOYMENT.md).


## Current completion safeguards

The local wrapper explicitly enables the provisioned numeric student identity
convention. Production requires an institutional implementation of
`api.identity.AuthenticatedIdentityResolver` and rejects that demo convention.
Real student reads recheck ERP active/discontinued status. Overall attendance
and recorded absent-period counts are supported. Teacher/HOD/Admin academic
access remains blocked: the dump has no populated authentication mapping or
proven end-to-end role/capability contract. See the latest audit in
[SCHEMA_MAPPING.md](SCHEMA_MAPPING.md) and results in
[RELEASE_VALIDATION.md](RELEASE_VALIDATION.md).
