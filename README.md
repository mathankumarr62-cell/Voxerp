# VoxERP — Person A Data Layer (MariaDB Edition)

This package implements the Person A data-layer foundation for VoxERP, using the real **ramco_academic_system** MariaDB database as the source of truth.

## Overview

**Previous Implementation:** SQLite mock database with seed data  
**Current Implementation:** Real MariaDB database (ramco_academic_system) with ~2763 students and full academic records  
**Status:** Production-ready, tested against real database

## Key Features

- **Real Database Integration:** Uses MariaDB connection pooling with parameterized queries
- **Safe Error Handling:** Explicit result codes ("ok", "not_found", "ambiguous", "no_data", "error") instead of silent failures
- **Subject Normalization:** "DBMS", "dbms", "db-ms" all match consistently
- **Ambiguous Name Handling:** When multiple students match a name, returns all candidates for clarification
- **Audit Trail:** Writes are logged to `voxerp_write_log` table with actor, action, timestamp
- **Environment-Based Configuration:** Database credentials from environment variables
- **Schema Discovery:** Automatic schema map generation for Person B's intent engine

## Setup

### 1. Install Dependencies

```powershell
cd "C:\Voxerp"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Configure Database Connection

The project reads its MariaDB configuration from the local `.env` file. Do not store the live password in source control or README files.

Example `.env`:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_local_password
DB_NAME=ramco_academic_system
VOXERP_USE_REAL_DB=False
```

For real MariaDB testing, set:

```env
VOXERP_USE_REAL_DB=True
```

### 3. Initialize Database

The application uses the selected backend automatically:

- SQLite/mock mode when `VOXERP_USE_REAL_DB=False`
- MariaDB real mode when `VOXERP_USE_REAL_DB=True`

Example:

```powershell
cd "C:\Voxerp"
$env:VOXERP_USE_REAL_DB = "False"
.\.venv\Scripts\python.exe -m pytest -q
```

The data layer reads credentials strictly from `.env` and uses the installed `mariadb` connector. It does not use `mysql.connector`.

## Database Schema Mapping

See [SCHEMA_MAPPING.md](SCHEMA_MAPPING.md) for detailed documentation of:
- Real table structures
- Column definitions
- Query patterns
- Example queries

Quick reference:

| Logical Entity | Real Table | Records |
|---|---|---|
| Students | `user_accounts_studentdetails` | ~2763 |
| Courses | `course_management_course` | ~200+ |
| Enrollment | `course_management_courseenrollment` | ~50k+ |
| Attendance | `student_management_daily_attendance` | ~200k+ |
| Exams | `examination_management_studentexam` | ~50k+ |
| Marks | `examination_management_studentmark` | ~500k+ |
| Timetable | `course_management_periodallocation` | ~500+ |
| Audit Log | `voxerp_write_log` | Created by Person A |
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
# Get all attendance records
result = get_attendance(student_id="12345")

# Get attendance for specific subject
result = get_attendance(student_id="12345", subject="DBMS")

# Returns: {"status": "ok"|"not_found"|"no_data", "rows": [...]}
```

### Marks

```python
# Get all exam marks
result = get_marks(student_id="12345")

# Get marks for specific subject
result = get_marks(student_id="12345", subject="DBMS")

# Returns: {"status": "ok"|"not_found"|"no_data", "rows": [...]}
```

### Timetable

```python
# Get timetable for student (uses their year/semester from profile)
result = get_timetable(student_id="12345")

# Returns: {"status": "ok"|"not_found"|"no_data", "rows": [...]}
```

### Mark Attendance (Write)

```python
result = mark_attendance(
    student_id="12345",
    subject="DBMS",
    date="2026-09-01",
    status="present",
    actor_id="teacher-1"
)

# Returns: {"status": "created"|"updated"|"unchanged"|"not_found"|"error"}
```

### Schema Map

```python
schema_map = build_schema_map()
# Returns: {"tables": {...}, "description": "...", "db_host": "...", ...}
```

## Running Tests

```powershell
# Run the full project test suite
cd "C:\Voxerp"
.\.venv\Scripts\python.exe -m pytest -q

# Run the SQLite/mock suite
$env:VOXERP_USE_REAL_DB = "False"
.\.venv\Scripts\python.exe -m pytest -q tests/test_db_adapter.py

# Run the MariaDB integration suite
$env:VOXERP_USE_REAL_DB = "True"
.\.venv\Scripts\python.exe -m pytest -q tests/test_db_adapter_mariadb.py
```

### Troubleshooting connection problems

- Confirm `.env` contains valid `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME`.
- Confirm the local MariaDB service is running and accepting TCP connections on `localhost:3306`.
- Confirm the configured user can authenticate using the installed `mariadb` library.
- Do not reintroduce `mysql.connector` or any `auth_gssapi_client` fallback.
- For live verification, run a direct Python probe:

```powershell
cd "C:\Voxerp"
.\.venv\Scripts\python.exe -c "import os, mariadb; from dotenv import load_dotenv; load_dotenv(); conn = mariadb.connect(host=os.getenv('DB_HOST','localhost'), port=int(os.getenv('DB_PORT','3306')), user=os.getenv('DB_USER','root'), password=os.getenv('DB_PASSWORD',''), database=os.getenv('DB_NAME','ramco_academic_system')); print(conn.cursor().execute('SELECT 1')); conn.close()"
```

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

The application will:
1. Load environment from `.env`
2. Initialize database tables
3. Serve the voice interface
4. Connect Person B's intent engine
5. Enforce Person C's RBAC rules

## Differences from SQLite Version

| Aspect | SQLite (Old) | MariaDB (New) |
|---|---|---|
| Database | `voxerp.db` (mock) | `ramco_academic_system` (real) |
| Students | 6 demo records | ~2763 real students |
| Connection | Direct file | Connection pool (max 5) |
| Schema | Simple mock tables | Full academic schema |
| Credentials | None | .env variables |
| Audit Log | `write_log` table | `voxerp_write_log` table |
| Demo Users | `demo_users` table | `voxerp_demo_users` table |
| Error Handling | SQLite exceptions | Explicit status codes |
| Query Safety | String concatenation | Parameterized queries |

## Compatibility

### Person B (Intent Engine / RBAC)

✅ **Compatible** - All adapter function signatures and return types unchanged
- `get_attendance(student_id, subject)` → returns same result shape
- `get_marks(student_id, subject)` → returns same result shape  
- `get_timetable(student_id)` → returns same result shape
- `mark_attendance(student_id, subject, date, status, actor_id)` → returns same result shape
- `build_schema_map()` → returns updated schema with real table structure

### Person C (Voice/Flask)

✅ **Compatible** - Routes and API unchanged
- `/users` → now fetches from `voxerp_demo_users`
- `/query` → uses new db_adapter, same request/response format
- `/confirm` → works with real attendance writes to MariaDB

## Important Notes

### For Real Student Testing

Real students in the database include names like:
- Vijayaguru S
- Vijayasri Vembu.T
- VIJAYA DHARSHINI S
- And many more...

Use `lookup_student(name="Vijay")` to find them. The function will return ambiguous results for similar names, which is expected behavior.

### Database Read-Only Safety

The adapter only writes to:
- `student_management_daily_attendance` - for marking attendance
- `voxerp_write_log` - for audit trail

All other tables are read-only. The real academic database remains the source of truth.

### Connection Pooling

The adapter uses a connection pool with max 5 connections. Each database operation:
1. Acquires a connection from pool
2. Executes query with parameters
3. Closes connection (returns to pool)

This is safe and efficient for concurrent access.

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
Database connection test failed: Access denied for user 'root'@'localhost'
```

**Solution:** Check `.env` file has correct DB_USER and DB_PASSWORD

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

- [ ] Advanced RBAC with class-level filtering
- [ ] Gemini-based intent engine
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
