# VoxERP — Sprint Plan

**Reality check first:** the full 4-week plan is the *right* long-term design, and you should still submit that document alongside this one — labeled as your Phase 2 roadmap. It shows the HOD you thought past the demo. But building all of it isn't possible in the time you have, and a demo that breaks live is worse than a smaller one that doesn't. This plan cuts hard to what can actually work end-to-end.

---

## What's IN (this is the whole scope — don't add to it mid-build)

- Voice in/out (Web Speech API)
- Mock DB with realistic seed data (students, subjects, attendance, marks)
- Intent engine: Gemini turns a spoken query into `{action, table, filters}` — no confidence scoring, no clarification loop
- Hard RBAC filter — a student can only ever see their own data, a teacher can see their class. Used before *and* after the data fetch, but it's one shared function, not two separate systems
- **One working write action**: "mark [student] absent" — with a spoken yes/no confirmation before it commits
- A simple write log (who did what, when) — one table, no admin viewer
- A rehearsed demo script

## What's OUT (say this explicitly in your submission — don't hide it)

- Real JWT auth → **replaced with a simple "select your demo user" dropdown** (student1 / student2 / teacher1). This is fine for a proposal demo; call it out as a stub for real login.
- Ambiguous-intent clarification loop → if the intent engine gets it wrong, it says "I couldn't find that" instead of asking a follow-up. Documented as Phase 2.
- Confidence scoring, multi-retry state machine → confirmation is a plain "did I hear yes or no" keyword check, not an LLM judgment call. Faster to build, more reliable live.
- File-fetch (notes/certificates), API adapter, multiple write types (only attendance, not marks) → documented as Phase 2.
- Real ERP integration → not possible without the HOD's team involved anyway. Mock data only, explicitly.
- Audit log viewer, rollback/undo, regional language → all Phase 2.

**Cut-further rule:** if the read path (voice → answer) isn't working end-to-end by the time you're roughly halfway through your available time, drop the write/confirmation feature entirely and demo reads only. A solid read-only demo beats a broken write demo — don't gamble the whole thing on the harder half.

---

## Role Split (exactly as given)

**Person A — Data & Backend Foundation:** Data Access Layer (`db_adapter.py`, `api_adapter.py`, `file_adapter.py`), mock database + seed data, schema map generator
**Person B — Intelligence Layer:** intent engine (Gemini integration, prompt design), RBAC logic (student vs teacher access rules), response generator
**Person C — Voice Interface & Integration:** frontend (mic button, Web Speech API, UI), Flask routes (`app.py`), end-to-end testing

Everything below is built strictly within these three boundaries. Two things that don't have an explicit line in your split are placed by nearest fit, not reassigned: **demo-user records live in the mock database, so they're Person A's** (same layer as seed data). **The confirm-step yes/no listener is part of the Flask routes tying everything together, so it's Person C's** (same layer as `app.py`).

---

## Step 0 — All 3 together, before anyone writes code

- [ ] Agree the minimal contract, one shared doc, 10 minutes:
  - Adapter functions: `get_attendance(student_id, subject)`, `get_marks(student_id, subject)`, `get_timetable(student_id)`, `mark_attendance(student_id, subject, date, status)`
  - Intent JSON shape: `{"action": "read"|"write", "table": "attendance"|"marks"|"timetable", "filters": {...}}`
  - One route: `POST /query` — takes `{text, user_id, role}`, returns `{reply_text}`

---

## Edge Cases — Handle These From the Start, Don't Bolt On Later

Every one of these is a plausible thing to happen during a live demo. The rule: every layer should fail by *saying something sensible out loud*, never by hanging silently or crashing. Silence in front of a panel reads as broken even if the bug is trivial.

### Person A — Data layer edge cases
- [ ] Adapter called with a student_id or subject that doesn't exist in the seed data → return an explicit "not found" result, not an empty crash or a raw `None`
- [ ] Query returns zero rows (e.g. no attendance recorded yet for that subject) → return a clear "no data" result, distinct from "not found" — B's response generator needs to tell these apart
- [ ] Subject name case/spacing mismatches ("dbms" vs "DBMS" vs "DB MS") → normalize (lowercase + strip) before matching, since STT output won't match your seed data casing reliably
- [ ] Same write requested twice in a row (double confirmation, or double mic trigger) → check if the state already matches before writing again; log it once, not twice
- [ ] Any adapter call missing a required field → raise a clear, catchable error rather than a raw DB exception, so B/C can turn it into a spoken message

### Person B — Intelligence layer edge cases
- [ ] Gemini returns text that isn't valid JSON (happens more than you'd expect) → wrap every parse in try/except; on failure, return a fallback "I couldn't understand that request" intent rather than letting the exception propagate
- [ ] Gemini API call itself fails or times out (network blip, rate limit) → catch it, return the same fallback intent, log it so you notice if it's happening a lot during testing
- [ ] Transcribed text is empty or just noise (STT sometimes returns `""` or garbage on silence) → check for this before calling Gemini at all; skip straight to "I didn't catch that"
- [ ] Query asks for something outside scope entirely ("what's the weather", "tell me a joke") → intent engine should classify this as unsupported and say so, not force it into a table/filter guess
- [ ] **Query phrased to reach another student's data** ("show me Priya's marks" from a student token) → this must be caught by RBAC regardless of how naturally it's phrased; write this as an explicit test case, not an assumption
- [ ] Adapter returns "no data" vs "not found" (see A's note above) → response generator must phrase these differently ("you don't have any recorded absences" vs "I couldn't find that subject")

### Person C — Voice/routes edge cases
- [ ] Browser denies mic permission → show a visible message, don't fail silently
- [ ] STT times out or transcribes nothing → don't send an empty request to the backend; show/say "I didn't catch that, try again"
- [ ] Backend call itself times out or errors (500) → frontend needs a timeout and a spoken fallback ("something went wrong, please try again"), not an infinite spinner
- [ ] User speaks again while TTS is still talking → at minimum, ignore new input until playback finishes; don't let two requests race each other
- [ ] Confirmation step gets something other than a clean yes/no ("maybe", "hold on", background noise transcribed as gibberish) → treat as unclear, ask once more, then abort — never default to "yes" on an unclear reply, that's the one direction this must never fail toward
- [ ] No demo user selected before a query is sent → block the request client-side with a clear message, don't send it through with a null user

### Shared — test these explicitly during full-team testing
- [ ] Every layer's failure path produces a spoken message, not silence or a stuck UI
- [ ] The "student asking for another student's data" case, tested with several different phrasings, not just one
- [ ] The "unclear confirmation reply" case, tested with a genuinely ambiguous answer, confirming it never defaults to executing the write
- [ ] One deliberately broken input at each layer (bad student name, gibberish query, interrupted mic) run in front of the whole team at least once before the actual demo, so nobody's seeing a failure for the first time on demo day

---

## Person A — Data Access Layer, Mock DB, Schema Map

1. [ ] Create the repo and push a skeleton so B and C can pull
2. [ ] Build the SQLite schema + seed data — 5–6 fake students, 3 subjects, a realistic mix of attendance and marks records
3. [ ] Add demo user records to the same DB (id, role, name) — this is what C's frontend will let someone pick from, and what B's RBAC logic checks against
4. [ ] Write the 4 adapter functions (`db_adapter.py`) against real queries on that seed data — return real rows, not placeholders, since B builds directly against these shapes
5. [ ] Build the schema map generator — a function that reads the mock DB and outputs a short JSON/text description of what tables and fields exist, for B's intent engine to use as context
6. [ ] Hand off to B: adapter functions + schema map, ready to be called
7. [ ] Add `mark_attendance()` to the adapter layer once B confirms write-intents are being classified
8. [ ] Add a simple write log table (actor, action, target, timestamp) and call it from within the write adapter, before the write commits
9. [ ] Join full-team testing: verify the RBAC boundary tests and the write-confirm flow from the data side — check the DB state directly to confirm blocked queries never touched the wrong row
10. [ ] Write your part of the README: schema, seed data, adapter functions, schema map

---

## Person B — Intent Engine, RBAC, Response Generator

1. [ ] Confirm the Gemini API key works — one test call from a standalone script, before building anything on top of it
2. [ ] Once A delivers the schema map: build the intent engine — one Gemini prompt using the query + schema map + role, returning the agreed JSON shape
3. [ ] Test the intent engine against 10 sample queries — confirm the JSON parses every time, not just usually
4. [ ] Build the RBAC logic — a function that takes the role, user_id, and the intent's requested filters, and constrains them so a student can only ever reach their own data and a teacher only their class. This is called before every adapter call.
5. [ ] Build the response generator — takes the adapter's returned data and turns it into one spoken sentence. Use Gemini if its output is consistent in your testing; fall back to a plain string template if it isn't — reliability matters more than polish under this deadline.
6. [ ] Hand off to C: intent engine + RBAC + response generator, ready to be called in sequence
7. [ ] Add write-intent classification to the intent engine (`action: "write"` for commands like "mark X absent")
8. [ ] Write the exact confirmation question text ("Mark Vijay absent for today — say yes or no") and hand the exact wording to C, since they build the keyword listener against it
9. [ ] Join full-team testing: throw varied and deliberately ambiguous queries at the intent engine, note anything it misreads or where RBAC lets through more than it should
10. [ ] Write your part of the README: intent engine, RBAC logic, response generator

---

## Person C — Frontend, Flask Routes, End-to-End Testing

1. [ ] Get Web Speech API STT/TTS working in a blank HTML page — say something, see it transcribed, hear something spoken back, no backend yet
2. [ ] Build the `/query` Flask route skeleton
3. [ ] Wire the frontend to POST transcribed text + selected demo user to the route, speaking back whatever comes back (placeholder response is fine at first)
4. [ ] Once A's adapters and B's intent engine + RBAC + response generator exist: connect the full read chain — voice → intent → RBAC → adapter → response → voice out
5. [ ] Get one full read query working live, end to end, in front of A and B: "What's my attendance in DBMS?" for a student demo user — this is the checkpoint the whole write feature depends on; don't move to write handling until this is solid
6. [ ] Build the confirm step: speak B's confirmation question, listen for a yes/no keyword match (exact match, not an LLM judgment call — faster and more reliable), branch to execute-and-log or abort-and-notify
7. [ ] Get the full write flow working live: "Mark Vijay absent" → confirms → writes → speaks confirmation; saying "no" makes zero changes and says so
8. [ ] Lead full-team testing: 8–10 varied read queries across both demo roles; explicit RBAC-boundary attempts (student1 asking for student2's data, must be refused every time); the write-confirm flow run 5 times each for yes and no; budget real time to fix what breaks
9. [ ] Write the demo script: one read query, one RBAC-blocked attempt shown refusing, one write with confirmation, one write denial
10. [ ] Rehearse the script with A and B on the actual machine you'll demo from

---
