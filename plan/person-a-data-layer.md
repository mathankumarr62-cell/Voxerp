# VoxERP — Person A: Data & Backend Foundation

**Layer owned:** Data Access Layer, Mock DB, Schema Map
**Not owned (backend but different layers):** Flask routes / `/query` endpoint (Person C), Intent engine / Gemini / RBAC logic / response generator (Person B)

---

## Deliverables

- `db_adapter.py` — 4 adapter functions
- `api_adapter.py`, `file_adapter.py` — stubs per original split (out of scope for this sprint, not built)
- SQLite schema + seed data
- Demo user records
- Schema map generator
- Write log table
- Your section of the README

---

## Build Order

1. [ ] Create the repo and push a skeleton so B and C can pull
2. [ ] Build the SQLite schema + seed data — 5–6 fake students, 3 subjects, a realistic mix of attendance and marks records
3. [ ] Add demo user records to the same DB (id, role, name) — feeds C's dropdown and B's RBAC checks
4. [ ] Write the 4 adapter functions (`db_adapter.py`) against real queries on that seed data — return real rows, not placeholders:
   - `get_attendance(student_id, subject)`
   - `get_marks(student_id, subject)`
   - `get_timetable(student_id)`
   - `mark_attendance(student_id, subject, date, status)` *(added in step 7)*
5. [ ] Build the schema map generator — reads the mock DB, outputs a short JSON/text description of tables and fields for B's intent engine to use as context
6. [ ] Hand off to B: adapter functions + schema map, ready to be called
7. [ ] Add `mark_attendance()` to the adapter layer once B confirms write-intents are being classified
8. [ ] Add a simple write log table (actor, action, target, timestamp) and call it from within the write adapter, before the write commits
9. [ ] Join full-team testing — verify RBAC boundary tests and the write-confirm flow from the data side; check DB state directly to confirm blocked queries never touched the wrong row
10. [ ] Write your part of the README: schema, seed data, adapter functions, schema map

---

## Edge Cases — Build In From the Start

Every layer must fail by *saying something sensible*, never by hanging silently or crashing.

- [ ] Adapter called with a student_id or subject that doesn't exist in seed data → return an explicit **"not found"** result, not an empty crash or raw `None`
- [ ] Query returns zero rows (e.g. no attendance recorded yet) → return a clear **"no data"** result, distinct from "not found" — B's response generator needs to tell these apart
- [ ] Subject name case/spacing mismatches ("dbms" vs "DBMS" vs "DB MS") → normalize (lowercase + strip) before matching, since STT output won't match seed data casing reliably
- [ ] Same write requested twice in a row (double confirmation, or double mic trigger) → check if state already matches before writing again; log once, not twice
- [ ] Any adapter call missing a required field → raise a clear, catchable error rather than a raw DB exception, so B/C can turn it into a spoken message

---

## Shared Testing (join with full team)

- [ ] Every layer's failure path produces a spoken message, not silence or a stuck UI
- [ ] "Student asking for another student's data" case, tested with several phrasings
- [ ] "Unclear confirmation reply" case — confirm it never defaults to executing the write
- [ ] One deliberately broken input at each layer, run in front of the whole team before demo day

---

## Contract to Agree Before Anyone Codes (with A, B, C together)

- Adapter functions: `get_attendance(student_id, subject)`, `get_marks(student_id, subject)`, `get_timetable(student_id)`, `mark_attendance(student_id, subject, date, status)`
- Intent JSON shape: `{"action": "read"|"write", "table": "attendance"|"marks"|"timetable", "filters": {...}}`
- One route: `POST /query` — takes `{text, user_id, role}`, returns `{reply_text}`

---

## Notes

- Demo user records and the write log aren't named in the original role split but are placed with A by nearest fit (same layer as seed data / write adapter).
- The "not found" vs "no data" distinction is the one thing B directly depends on — confirm the exact return shape with B early.
- Your layer can be built and tested standalone (steps 1–6, 8) with a script that calls adapters directly and prints results — no need for B or C's code to be running.
