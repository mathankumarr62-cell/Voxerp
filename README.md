# VoxERP — Person A Data Layer (MariaDB Edition)

This package implements the Person A data-layer foundation for VoxERP, using the real **ramco_academic_system** MariaDB database as the source of truth.

## Overview

**Local mode:** SQLite fixtures for controlled tests.

**Real mode:** MariaDB `ramco_academic_system` for academic READ operations.

**Status:** Person A backend integration is validated with SQLite and local MariaDB READs. B's reviewed intent/RBAC/router modules are integrated. Actual Gemma inference and connectivity from B/C's remote hosts remain runtime handoff checks; this is not a claim of production deployment.

## Key Features

- **Real Database Integration:** Uses direct MariaDB connections with parameterized queries; no connection pool is implemented
- **Safe Error Handling:** Explicit result codes ("ok", "not_found", "ambiguous", "no_data", "error") instead of silent failures
- **Subject Normalization:** "DBMS", "dbms", "db-ms" all match consistently
- **Ambiguous Name Handling:** When multiple students match a name, returns bounded candidates for clarification
- **Audit Trail:** SQLite attendance changes are logged to `write_log`; the MariaDB attendance path does not insert an audit-log row
- **Environment-Based Configuration:** Database credentials from environment variables
- **Schema Discovery:** Automatic schema map generation for Person B's intent engine

## Setup

### 1. Install Dependencies

```powershell
cd "C:\Voxerp"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Configure Database Connection

The project loads `.env` without overriding existing process environment variables. Do not store the live password in source control or README files.

Example `.env`:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_local_password
DB_NAME=ramco_academic_system
VOXERP_USE_REAL_DB=False
VOXERP_ALLOW_REAL_WRITES=False
```

For authorized real MariaDB READ validation, use an existing provisioned account and the private database host. Real student reads require an authenticated, authorized identity; browser-supplied demo identity is for local fixtures. Set:

```env
VOXERP_USE_REAL_DB=True
VOXERP_ALLOW_REAL_WRITES=False
VOXERP_INITIALIZE_DATABASE=False
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for Tailscale/private-network checks and proposed production configuration. MariaDB port 3306 must never be exposed publicly.

### 3. Initialize Database

The application uses the selected backend automatically:

- SQLite/mock mode when `VOXERP_USE_REAL_DB=False`
- MariaDB real mode when `VOXERP_USE_REAL_DB=True`

Example:

```powershell
cd "C:\Voxerp"
$env:VOXERP_USE_REAL_DB = "False"
$env:VOXERP_ALLOW_REAL_WRITES = "False"
$env:VOXERP_INITIALIZE_DATABASE = "False"
.\.venv\Scripts\python.exe -m pytest -q tests/test_db_adapter.py
```

The adapter uses the installed `mariadb` connector. `DB_CONFIG` is captured from the environment at import time after loading `.env`; restart the process after configuration changes. Local development startup seeds SQLite when initialization is enabled. With real writes disabled, real `initialize_database()` returns `disabled` without creating tables.

## Database Schema Mapping

See [SCHEMA_MAPPING.md](SCHEMA_MAPPING.md) for detailed documentation of:
- Real table structures
- Column definitions
- Query patterns
- Example queries

Quick reference (existing counts are historical, not current validation):

| Logical Entity | Real Table | Records |
|---|---|---|
| Students | `user_accounts_studentdetails` | ~2763 |
| Courses | `course_management_course` | ~200+ |
| Enrollment | `course_management_courseenrollment` | ~50k+ |
| Overall daily attendance | `student_management_daily_attendance` | ~200k+ |
| Subject/hour attendance | `student_management_hourattendance` | Not revalidated |
| Exams | `examination_management_studentexam` | ~50k+ |
| Student-facing marks | `examination_management_overallconsolidaterecord` | Not revalidated |
| Timetable | `course_management_periodallocation` | ~500+ |
| Legacy audit object | `voxerp_write_log` | Creation code exists; attendance writes do not populate it |
| Demo Users | `voxerp_demo_users` | Demo data |

## Data Access Layer API

### Student Lookup

```python
# Lookup by student ID
result = lookup_student(student_id="12345")

# Lookup by name (fuzzy match)
result = lookup_student(name="Vijay")

# Returns: {"status": "ok"|"not_found"|"ambiguous"|"error", "student": {...}, "candidates": [...]}
```

### Course Lookup

```python
# Lookup by course code
result = lookup_course(course_code="CS101")

# Lookup by title
result = lookup_course(title="Data Structures")
```

### Student Enrollment

```python
result = get_enrollment(student_id="12345")
# Returns: {"status": "ok"|"no_data", "enrollments": [...]}
```

### Attendance

```python
# Get overall daily attendance in MariaDB mode
result = get_attendance(student_id="12345")

# Get attendance for specific subject
result = get_attendance(student_id="12345", subject="DBMS")

# Returns: {"status": "ok"|"not_found"|"no_data", "rows": [...]}
```

Subject-specific MariaDB reads use `student_management_hourattendance` joined to courses and match normalized code/title. Daily attendance has no course field. SQLite uses its local `attendance` fixture table.

### Marks

```python
# Get all consolidated assessment marks
result = get_marks(student_id="12345")

# Get marks for specific subject
result = get_marks(student_id="12345", subject="DBMS")

# Returns: {"status": "ok"|"not_found"|"no_data", "rows": [...]}
```

MariaDB marks come from `examination_management_overallconsolidaterecord`, filtered by `student_id` and joined by `course_id` to courses. Theory, activity and practical comma-separated assessment fields are parsed into result rows. Raw question-level marks, including `examination_management_studentinternalmark`, are not blindly summed.

### Timetable

```python
# Get timetable for student (uses their year/semester from profile)
result = get_timetable(student_id="12345")

# Returns: {"status": "ok"|"not_found"|"no_data", "rows": [...]}
```

### Mark Attendance (Write)

This example is for a controlled SQLite fixture only (`VOXERP_USE_REAL_DB=False`). Real ERP writes remain disabled; the MariaDB path is not approved for production use.

```python
result = mark_attendance(
    student_id="student-1",
    subject="DBMS",
    date="2026-09-01",
    status="present",
    actor_id="teacher-1",
    period=1
)

# Returns created/updated/unchanged on success; also not_found/error/invalid/disabled.
# Missing required arguments raise ValueError.
```

In MariaDB mode, `period` is required because course-specific attendance is
stored in `student_management_hourattendance`. The adapter will not guess a
period or write a course-less daily attendance record.

### Schema Map

```python
schema_map = build_schema_map()
# Returns: {"tables": {...}, "description": "...", "db_host": "...", ...}
```

## Running Tests

### Local SQLite tests and safe collection

Use the project virtual environment. These process settings override `.env` and prevent Flask initialization during collection:

```powershell
cd "C:\Voxerp"
$env:VOXERP_USE_REAL_DB = "False"
$env:VOXERP_ALLOW_REAL_WRITES = "False"
$env:VOXERP_INITIALIZE_DATABASE = "False"
.\.venv\Scripts\python.exe -m pytest --collect-only -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest -q tests/test_db_adapter.py
```

The focused adapter suite creates and removes a temporary SQLite fixture. It does not validate real ERP data. `pytest.ini` excludes `transaction_test.py` and `transaction_engine_test.py` from automatic discovery. Those preserved manual probes contain direct MariaDB INSERTs and must not be run against the real ERP; rollback is not permission to write.

### Real ERP READ validation

Do not run the complete MariaDB suite as a read-only check: existing tests call initialization or expect write success. `tests/test_attendance_write_transaction.py` is enabled by real-database mode alone and expects writes. Keep `VOXERP_ALLOW_REAL_WRITES=False`; never enable it to make these tests pass.

First verify the private connection as described in [DEPLOYMENT.md](DEPLOYMENT.md). Then run the dedicated validator below to check academic reads and the integrated Flask/RBAC path. Record actual results separately from SQLite results. A direct adapter check or `/healthz` (`SELECT 1`) alone does not prove that application path.

## Error Handling

The adapter returns explicit status codes for all operations:

- **"ok"** - Operation succeeded, data included
- **"not_found"** - Resource (student/course/etc) doesn't exist
- **"ambiguous"** - Multiple matches found, disambiguation needed
- **"no_data"** - Resource exists but no records found (e.g., no attendance)
- **"error"** - Database error occurred, message included

Example error handling:

```python
result = get_attendance("12345", "DBMS")
if result["status"] == "not_found":
    # Student doesn't exist
    print(result["message"])
elif result["status"] == "no_data":
    # Student exists but no attendance recorded
    print("No attendance recorded yet")
elif result["status"] == "ok":
    # Success - process rows
    for row in result["rows"]:
        print(row)
else:  # "error"
    # Database error
    print(f"Error: {result['message']}")
```

## Running the Application

Start the Flask backend (also starts web interface):

```bash
python app.py
```

Then open http://localhost:5050 in your browser.

The current `/query` route uses trusted identity, B's IntentEngine, B's authorization/DataRouter, the finalized adapter and B's response generator. Overall attendance and all-course marks are accepted without a subject. `/confirm` verifies the signed action and current identity, then invokes B's authorization again. Importing Flask does not connect to or initialize a database. The root route serves only `index.html`; project files are not exposed as static assets.

For local UI startup, set `VOXERP_USE_REAL_DB=False`, `VOXERP_INITIALIZE_DATABASE=True` and `VOXERP_OFFLINE_MODE=True` in the launching process, then run `app.py`. This explicitly selects B's existing deterministic demo parser; no fake client is used for real ERP inference. Initialization defaults to False. Demo identities are checked against the SQLite fixture and are rejected entirely in real ERP mode. Production startup and trusted proxy requirements are described in [DEPLOYMENT.md](DEPLOYMENT.md).

## SQLite and MariaDB modes

| Aspect | SQLite local fixture | Real MariaDB |
|---|---|---|
| Database | `voxerp.db` (mock) | `ramco_academic_system` (real) |
| Students | Seeded fixture identities | Real academic records |
| Connection | Direct file connection | Direct connector connection; no pool |
| Schema | Simple mock tables | Full academic schema |
| Credentials | None | Environment, optionally loaded from `.env` |
| Audit Log | Attendance changes insert into `write_log` | Attendance path does not insert into `voxerp_write_log` |
| Demo Users | `/users` lists fixture identities from `students` | Demo users/identity disabled; trusted proxy mapping required |
| Error Handling | SQLite exceptions | Explicit status codes |
| Query Safety | Bound values | Bound values |

## Compatibility

### Person B (Intent Engine / RBAC)

B modules were recovered unchanged from reviewed PR head `e8ba64b62f8d2ccd1bd514a1a9673bb0407da6cc`. `db_adapter.py` remains byte-for-byte at `37f04ee`; PR #2's adapter/fixtures were not imported.
- `get_attendance(student_id, subject)` → returns same result shape
- `get_marks(student_id, subject)` → returns same result shape  
- `get_timetable(student_id)` → returns same result shape
- `mark_attendance(student_id, subject, date, status, actor_id)` → returns same result shape
- `build_schema_map()` → returns updated schema with real table structure

### Person C (Voice/Flask)

Current Flask routes (voice/browser end-to-end validation remains with C):
- `/users` → now fetches from `voxerp_demo_users`
- `/query` → uses new db_adapter, same request/response format
- `/confirm` calls the attendance adapter; real ERP writes remain disabled

## Important Notes

### For Real Student Testing

Real students in the database include names like:
- Vijayaguru S
- Vijayasri Vembu.T
- VIJAYA DHARSHINI S
- And many more...

Use `lookup_student(name="Vijay")` to find them. The function will return ambiguous results for similar names, which is expected behavior.

### Database Read-Only Safety

Keep `VOXERP_ALLOW_REAL_WRITES=False` (or unset). With that setting, real attendance mutation and initialization are disabled. Target/course validation can still issue SELECTs before `mark_attendance()` returns `disabled` or a validation error.

A gated MariaDB INSERT/UPDATE path exists for `student_management_hourattendance`, but it is not approved as a safe production write workflow. It does not insert an audit-log row, and its UPDATE references `updated_at`, absent from the documented hourly columns. These require separate validation before any future write approval. The gated initializer can create `voxerp_write_log` and `voxerp_demo_users` and seed demo users; do not enable it on the real ERP.

The adapter assumes its caller has authorized the target student. RBAC and confirmation/reauthorization belong to Person B; direct adapter examples do not authorize application users to access arbitrary students.

### Connection management

`_get_connection()` opens a direct `mariadb.connect(**DB_CONFIG)` connection. Adapter operations close owned connections in `finally` blocks. Attendance functions can accept a caller-owned MariaDB connection, which the caller must close. No connection pooling is implemented.

### .gitignore

The following are excluded from version control:
- `.env` - Database credentials
- `*.db` - SQLite files  
- `__pycache__/` - Python cache
- `.pytest_cache/` - Test cache

Never commit database passwords or credentials.

## Troubleshooting

### Connection Failed

```python
>>> test_connection()
Database connection test failed
False
```

**Solution:** Follow the ordered private-network checks in [DEPLOYMENT.md](DEPLOYMENT.md). The adapter suppresses connector details; a generic failure does not establish a password problem.

### Student Not Found

```python
>>> lookup_student(name="Unknown Name")
{"status": "not_found"}
```

**Solution:** Use `get_attendance()` or `get_marks()` with a valid student ID to verify the student exists

### Too Many Results (Ambiguous Match)

```python
>>> lookup_student(name="Vijay")
{"status": "ambiguous", "candidates": [...]}
```

**Solution:** Person B's intent engine should ask for clarification using candidate list

## Future Work (Phase 2)

- [ ] B validates actual Gemma/model-host runtime; C validates voice/UI on the deployed service
- [ ] Multi-language support
- [ ] Lab attendance tracking
- [ ] GPA and performance analytics
- [ ] Student feedback collection
- [ ] Course recommendations

---

**Last Updated:** September 2026  
**Database Version:** MariaDB 12.3.3  
**Verified Database:** ramco_academic_system  
**Data Layer Owner:** Person A

## Reproducible READ validation and runtime handoff

After verifying Tailscale and TCP connectivity, run explicitly (never part of pytest):

```powershell
.\.venv\Scripts\python.exe scripts/validate_real_reads.py --student-id 917 --subject IT25201
```

This uses existing protected credentials, forces each MariaDB session read-only,
and forces real writes off. It checks adapter data, historical marks expectations,
Flask routing and cross-student denial without printing academic records or secrets.
The Flask check injects an inference stub through B's existing client interface;
it does not certify model quality. Ordinary pytest forces SQLite mode and blocks
MariaDB/network connections, even if `.env` selects the real ERP.

`google-genai==1.75.0` supplies B's unconditional SDK import and was validated on
this Windows Python environment. No cloud client is automatically constructed.
`requirements-gemma.txt` is optional for B's model host: B must establish its exact
MLX-VLM version, supported OS/hardware and model revision before deployment.
The recovered default model identifier is `mlx-community/gemma-4-e4b-it-4bit`;
actual loading/inference has not been validated here. Models load lazily on the
first request, not during import or pytest collection. Without a model, requests
fail closed; explicit SQLite offline mode is available for development.

All confirmations now use signed tokens. SQLite demos use a process-local key
unless one is configured; restarting invalidates those tokens. Proxy deployments
must configure `VOXERP_PENDING_SECRET`. Teacher access remains fail-closed because
B has no verified teacher-to-class mapping; this release does not invent one.
See [RELEASE_VALIDATION.md](RELEASE_VALIDATION.md) for release evidence and limits.
