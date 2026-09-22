# Local demo recovery — 2026-09-22

The reported attendance failure came from the MariaDB layer, not authentication
or intent parsing. The live Django process used `~/Developer/Voxerp`; the IDE
checkout was `~/Desktop/Voxerp`. The live adapter swallowed this exception and
the response generator rendered its `status=error` as the reported generic text:

```text
File "db_adapter.py", line 755, in get_attendance
    cursor.execute(...)
File "mariadb/cursors.py", line 351, in execute
    self._readresponse()
mariadb.OperationalError: Incorrect information in file:
    './ramco_academic_system/student_management_hourattendance.frm'
```

The Developer clone had 52 empty `.frm`/`.ibd` files, including the attendance
and marks definitions. The Desktop original had no empty table files. The
attendance and marks tablespaces were byte-identical between copies. The
damaged clone was preserved; its server was stopped gracefully and the intact
Desktop clone started on `127.0.0.1:3307`. No ERP records were changed. Server
read-only mode and the demo account's SELECT-only grants were verified.

Startup now rejects empty table files, with regression coverage for both file
types and an intact running clone. This is a preflight check, not proof of full
database integrity.

Actual local Gemma also exposed a separate issue: `Show my AD3491 marks` placed
the course code in `student_name`. Recovery now recognizes the explicit
`my <course code> marks/attendance` construction when that name equals the code.
It preserves other names, explicit student IDs, and existing valid subjects.
Recovery runs after course-as-ID recovery so the two rules do not interfere.
Regression tests exercise the full parse path and authorization together.

The intact dataset has no AD3491 marks or attendance for student 917. Correct
behavior is an authenticated no-data response, not fabricated results. The
existing read validator passed populated IT25201 marks and attendance, historical
mark expectations, the separately approved student 44 timetable, service/adapter
response agreement, and cross-student denial. Its inference remains explicitly
stubbed; separate validation used actual cached local Gemma with no cloud client.

Final automated checks: 134 passed, 26 intentionally skipped live-database tests,
and zero network/MariaDB attempts in ordinary pytest. Targeted Person B, Django
API, adapter, release, and security tests passed. Python compilation, Django
system checks, migration consistency, and pending-migration checks passed.
Actual Gemma responses for both AD3491 marks phrasings, both attendance
phrasings, Distributed Computing attendance, own timetable, and populated
IT25201 marks/attendance matched the adapter's results. Bob Smith and student 2
queries were denied.

Browser acceptance must not be inferred from backend tests. The saved password
in the running Developer checkout was empty, and the Desktop saved password did
not match either account database. Current credentials were requested for real
login verification. Physical microphone capture and audible playback require
hardware verification; automated speech lifecycle tests do not establish them.
