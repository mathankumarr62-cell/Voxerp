# VoxERP — Person A Deliverable

This package implements the Person A data-layer foundation for the VoxERP sprint demo.

## Included pieces

- SQLite-backed mock database with seed data for students, subjects, attendance, marks, timetable, demo users, and a write log
- Adapter functions for reading and writing attendance data
- Normalization for subject names so inputs like "DBMS", "dbms", and "DB MS" resolve consistently
- Explicit result shapes for the two important edge cases:
  - "not_found" for unknown students or subjects
  - "no_data" when the student exists but no records are present
- A schema map generator that exposes the available tables and columns to the rest of the team

## Adapter API

- `get_attendance(student_id, subject)`
- `get_marks(student_id, subject)`
- `get_timetable(student_id)`
- `mark_attendance(student_id, subject, date, status)`

## Quick start

```bash
python db_adapter.py
```

The module initializes the SQLite database, seeds the demo data, and prints a short sample of the generated schema map.


## VoxERP — Person C Deliverable

This package implements the voice interface, Flask routing, and end-to-end wiring for the VoxERP sprint demo.

### Included pieces

- Web Speech API integration (`index.html`) — speech-to-text for voice input, speech synthesis for spoken replies
- Flask backend (`app.py`) exposing the shared `/query` contract: `POST /query` takes `{text, user_id, role}`, returns `{reply_text}`
- `/users` route — serves the demo user list (id, role, name) for the frontend dropdown
- `/confirm` route — handles the yes/no confirmation step for write actions, separate from the main query flow so a write is never committed without an explicit confirmation
- Stub intent parser and stub RBAC layer (keyword-based, documented below) standing in for Person B's real Gemini-based intent engine and RBAC logic — same input/output shape, swappable without touching the frontend or routes
- Full write-confirmation flow: a write request never executes immediately. It returns a spoken confirmation question and a `pending` action; the frontend automatically re-listens for the answer

### Edge cases handled

- Mic permission denied → visible status message, not a silent failure
- STT returns nothing / times out → spoken "I didn't catch that, try again," no empty request sent to backend
- Backend request times out (10s) or errors → spoken fallback, no infinite spinner
- User speaks while TTS is still talking → new mic input is ignored until playback finishes
- Unclear confirmation reply (not an exact yes/no) → asked once more, then aborts with no changes made — confirmation never defaults to "yes" on an ambiguous answer, including doubled/echoed transcription
- No demo user selected before a query → blocked client-side with a clear message

### Routes

- `GET /` — serves the frontend
- `GET /users` — returns demo user list
- `POST /query` — takes `{text, user_id, role}`, returns `{reply_text}`, or `{reply_text, requires_confirmation, pending}` for write actions awaiting confirmation
- `POST /confirm` — takes `{confirm: "yes"|"no", pending: {...}}`, commits or cancels the pending write

### Stub layers (documented per the sprint plan's "what's out" section)

The intent parser (`parse_intent`) and RBAC (`apply_rbac_read` / `apply_rbac_write`) in `app.py` are simple keyword-matching stubs, not the real Gemini-based intent engine or full RBAC logic Person B is responsible for. They follow the same `{action, table, filters}` contract so Person B's real implementation can be dropped in without changing any frontend or routing code. Current stub RBAC always restricts a student to their own `student_id`; a teacher role can target another student by name in a write ("mark Vijay absent"), but read RBAC does not yet do class-level scoping — documented as Phase 2 alongside the rest of the real RBAC.

### Quick start