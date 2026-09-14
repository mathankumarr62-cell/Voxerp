# VoxERP

VoxERP is a Django-based, voice-enabled academic ERP assistant. It answers only supported academic-data and policy questions; it is not a general chatbot.

## Architecture

`Django` owns login, sessions, CSRF protection, the web UI, and the JSON API. `IntentEngine` uses local Gemma to produce validated intent JSON. Deterministic `RBAC` authorizes that intent before the `DataRouter` selects either SQL or policy RAG. `db_adapter.py` is the only ERP integration layer and reads the existing MariaDB ERP schema. Policy documents in `rag/policy_documents/` are retrieval-only and can never grant access. Browser speech APIs provide optional STT/TTS; text input always remains available.

Django's local SQLite database (`voxerp_app.sqlite3`) is for users and sessions only. It is never used as the academic ERP database and Django migrations must never target the college MariaDB instance.

## Setup

Use Python 3.11+ and a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
python3 manage.py migrate
python3 manage.py createsuperuser
python3 manage.py runserver
```

For a local HTTP demo set `DEBUG=True` in your uncommitted `.env`; keep it `False` in deployment. Create each Django account with a username matching its ERP student ID (for example `student-1`). A staff account or a member of the `teacher` group is treated as a teacher, but remains denied until a verified teacher-to-class mapping exists.

Open `http://127.0.0.1:8000/`, sign in, and use the text box or microphone. Chrome-family browsers normally provide the Web Speech API. Other browsers show a clear fallback message and retain the text interface.

## Configuration and ERP safety

Copy `.env.example`; it contains placeholders only. Configure `DJANGO_SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and the `DB_*` values outside version control.

`VOXERP_USE_REAL_DB=True` enables adapter reads from the private MariaDB ERP. `VOXERP_ALLOW_REAL_WRITES` must remain `False` during development and testing. `VOXERP_OFFLINE_MODE=True` forces the isolated SQLite fixture, including when a real database is configured. Never expose MariaDB port 3306 publicly.

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
python3 -m unittest tests.test_person_b tests.test_person_b_additional
python3 -m unittest tests.test_app tests.test_offline_mode
```

The last command exercises the retained Flask compatibility layer in forced offline mode. New deployments use Django via `manage.py`; Flask remains only while those legacy tests exist.

## Troubleshooting

- **Redirected to login:** create/sign in to a Django user first.
- **Voice unavailable:** grant browser microphone permission or use text input.
- **Gemma unavailable:** install the Apple Silicon MLX stack appropriate to the host and model, or expect requests to fail safely as unsupported.
- **Database unavailable:** verify private/Tailscale connectivity and `DB_*` values; never change write safety settings to diagnose a connection.
