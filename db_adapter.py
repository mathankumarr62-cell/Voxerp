"""VoxERP Data Access Layer.

This module provides a single adapter API while allowing either a SQLite mock
backend for unit tests or the real MariaDB academic database when
VOXERP_USE_REAL_DB=True.
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import Any, Dict, Optional

from dotenv import load_dotenv
import mariadb


load_dotenv()

_DB_FILE = os.path.join(os.path.dirname(__file__), "voxerp.db")


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _real_db_enabled() -> bool:
    return _as_bool(os.getenv("VOXERP_USE_REAL_DB"), default=False)


def _get_db_config() -> Dict[str, Any]:
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "ramco_academic_system"),
    }


DB_CONFIG = _get_db_config()


def _sqlite_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _close_connection(conn) -> None:
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


def _get_connection():
    if not _real_db_enabled():
        return _sqlite_connect()

    try:
        return mariadb.connect(**DB_CONFIG)
    except mariadb.Error as exc:
        raise RuntimeError(f"Failed to connect to MariaDB: {exc}") from exc


def _normalize_subject(subject: Optional[str]) -> Optional[str]:
    if subject is None:
        return None
    compact = re.sub(r"[^a-z0-9]+", "", str(subject).strip().lower())
    return compact or None


def _student_record_to_dict(row) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        values = tuple(row)
    else:
        values = tuple(row)
    return {
        "id": values[0],
        "name": values[1],
        "reg_no": values[2],
        "batch": values[3],
        "year": values[4],
        "semester": values[5],
        "section": values[6],
        "email": values[7],
        "department_id": values[8],
    }


def _course_record_to_dict(row) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    values = tuple(row)
    return {
        "id": values[0],
        "course_code": values[1],
        "title": values[2],
        "year": values[3],
        "semester": values[4],
        "department_id": values[5],
    }


def _sqlite_migrate_schema(conn: sqlite3.Connection) -> None:
    required_columns = {
        "students": {
            "name": "TEXT",
            "reg_no": "TEXT",
            "batch": "TEXT",
            "year": "INTEGER",
            "semester": "INTEGER",
            "section": "TEXT",
            "email": "TEXT",
            "department_id": "INTEGER",
            "role": "TEXT",
            "class_name": "TEXT",
        },
        "attendance": {
            "student_id": "TEXT",
            "subject": "TEXT",
            "attendance_date": "TEXT",
            "status": "TEXT",
        },
        "write_log": {
            "actor": "TEXT",
            "action": "TEXT",
            "target": "TEXT",
            "subject": "TEXT",
            "attendance_date": "TEXT",
            "status": "TEXT",
        },
        "courses": {
            "course_code": "TEXT",
            "title": "TEXT",
            "year": "INTEGER",
            "semester": "INTEGER",
            "department_id": "INTEGER",
        },
        "enrollments": {
            "student_id": "TEXT",
            "course_id": "INTEGER",
            "enrollment_date": "TEXT",
            "course_code": "TEXT",
            "course_title": "TEXT",
            "year": "INTEGER",
            "semester": "INTEGER",
        },
        "timetable": {
            "student_id": "TEXT",
            "day": "TEXT",
            "section": "TEXT",
            "year": "INTEGER",
            "semester": "INTEGER",
            "period": "TEXT",
            "course_id": "INTEGER",
        },
        "marks": {
            "student_id": "TEXT",
            "exam_name": "TEXT",
            "course_code": "TEXT",
            "course_title": "TEXT",
            "date": "TEXT",
            "marks_obtained": "INTEGER",
            "max_marks": "INTEGER",
        },
    }

    for table_name, columns in required_columns.items():
        existing_columns = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")
        }
        for column_name, column_type in columns.items():
            if column_name not in existing_columns:
                conn.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                )

    marks_columns = {row[1] for row in conn.execute("PRAGMA table_info(marks)")}
    if {"course_code", "subject"}.issubset(marks_columns):
        conn.execute(
            "UPDATE marks SET course_code = subject WHERE course_code IS NULL AND subject IS NOT NULL"
        )
    if {"marks_obtained", "score"}.issubset(marks_columns):
        conn.execute(
            "UPDATE marks SET marks_obtained = score WHERE marks_obtained IS NULL AND score IS NOT NULL"
        )
    if {"max_marks", "marks_obtained"}.issubset(marks_columns):
        conn.execute(
            "UPDATE marks SET max_marks = 100 WHERE max_marks IS NULL AND marks_obtained IS NOT NULL"
        )

    timetable_columns = {row[1] for row in conn.execute("PRAGMA table_info(timetable)")}
    if {"period", "slot"}.issubset(timetable_columns):
        conn.execute(
            "UPDATE timetable SET period = slot WHERE period IS NULL AND slot IS NOT NULL"
        )


def _sqlite_seed() -> None:
    conn = _sqlite_connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id TEXT PRIMARY KEY,
                name TEXT,
                reg_no TEXT,
                batch TEXT,
                year INTEGER,
                semester INTEGER,
                section TEXT,
                email TEXT,
                department_id INTEGER,
                role TEXT,
                class_name TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT,
                subject TEXT,
                attendance_date TEXT,
                status TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS write_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT,
                action TEXT,
                target TEXT,
                subject TEXT,
                attendance_date TEXT,
                status TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY,
                course_code TEXT,
                title TEXT,
                year INTEGER,
                semester INTEGER,
                department_id INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT,
                course_id INTEGER,
                enrollment_date TEXT,
                course_code TEXT,
                course_title TEXT,
                year INTEGER,
                semester INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS timetable (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT,
                day TEXT,
                section TEXT,
                year INTEGER,
                semester INTEGER,
                period TEXT,
                course_id INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT,
                exam_name TEXT,
                course_code TEXT,
                course_title TEXT,
                date TEXT,
                marks_obtained INTEGER,
                max_marks INTEGER
            )
            """
        )
        _sqlite_migrate_schema(conn)

        conn.execute(
            "INSERT OR IGNORE INTO students (id, name, reg_no, batch, year, semester, section, email, department_id, role, class_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("student-1", "Alice Johnson", "2024001", "2024", 2, 3, "A", "alice@example.com", 1, "student", "CSE-A"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO students (id, name, reg_no, batch, year, semester, section, email, department_id, role, class_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("student-2", "Bob Smith", "2024002", "2024", 2, 3, "A", "bob@example.com", 1, "student", "CSE-A"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO students (id, name, reg_no, batch, year, semester, section, email, department_id, role, class_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("student-6", "Charlie Young", "2024006", "2024", 2, 3, "A", "charlie@example.com", 1, "student", "CSE-A"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO students (id, name, reg_no, batch, year, semester, section, email, department_id, role, class_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("teacher-1", "Teacher One", "T001", "2024", 2, 3, "A", "teacher@example.com", 1, "teacher", "CSE-A"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO courses (id, course_code, title, year, semester, department_id) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "DBMS", "Database Management Systems", 2, 3, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO attendance (student_id, subject, attendance_date, status) VALUES (?, ?, ?, ?)",
            ("student-1", "DBMS", "2026-08-20", "present"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO enrollments (student_id, course_id, enrollment_date, course_code, course_title, year, semester) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("student-1", 1, "2026-08-01", "DBMS", "Database Management Systems", 2, 3),
        )
        conn.execute(
            "INSERT OR IGNORE INTO marks (student_id, exam_name, course_code, course_title, date, marks_obtained, max_marks) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("student-1", "Unit Test 1", "DBMS", "Database Management Systems", "2026-08-15", 88, 100),
        )
        conn.execute(
            "INSERT OR IGNORE INTO timetable (student_id, day, section, year, semester, period, course_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("student-1", "Monday", "A", 2, 3, "period_1", 1),
        )
        conn.commit()
    finally:
        _close_connection(conn)


def check_connection() -> bool:
    """Check if the selected database backend is reachable."""
    conn = None
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        return True
    except Exception as exc:
        msg = str(exc)
        if "password" in msg.lower() or "auth" in msg.lower() or "access denied" in msg.lower():
            msg = "database authentication failed"
        print(f"Database connection test failed: {msg}")
        return False
    finally:
        _close_connection(conn)


def test_connection() -> bool:
    """Backward-compatible alias for older callers and tests."""
    return check_connection()


def initialize_database() -> Dict[str, Any]:
    if _real_db_enabled():
        conn = None
        try:
            conn = _get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS voxerp_write_log (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    actor_id VARCHAR(255) NOT NULL,
                    action VARCHAR(255) NOT NULL,
                    target_student_id VARCHAR(255),
                    course_id INT,
                    attendance_date DATE,
                    status VARCHAR(50),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_target_date (target_student_id, attendance_date),
                    INDEX idx_actor_time (actor_id, timestamp)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS voxerp_demo_users (
                    id VARCHAR(255) PRIMARY KEY,
                    role VARCHAR(50) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    real_student_id VARCHAR(255),
                    INDEX idx_role (role)
                )
                """
            )
            cursor.execute("SELECT COUNT(*) FROM voxerp_demo_users")
            if cursor.fetchone()[0] == 0:
                cursor.executemany(
                    "INSERT INTO voxerp_demo_users (id, role, name, real_student_id) VALUES (%s, %s, %s, %s)",
                    [
                        ("demo-student-1", "student", "Demo Student", None),
                        ("demo-student-2", "student", "Another Student", None),
                        ("demo-teacher-1", "teacher", "Demo Teacher", None),
                    ],
                )
            conn.commit()
            return {"status": "ok", "message": "Database initialized successfully"}
        except mariadb.Error as exc:
            return {"status": "error", "message": f"Failed to initialize database: {exc}"}
        finally:
            _close_connection(conn)

    _sqlite_seed()
    return {"status": "ok", "message": "SQLite mock database initialized successfully"}


def lookup_student(student_id: Optional[str] = None, name: Optional[str] = None, reg_no: Optional[str] = None) -> Dict[str, Any]:
    if not any([student_id, name, reg_no]):
        raise ValueError("student_id, reg_no, or name is required")

    if _real_db_enabled():
        conn = None
        try:
            conn = _get_connection()
            cursor = conn.cursor()

            if student_id:
                cursor.execute(
                    """
                    SELECT id, name, reg_no, batch, year, semester, section, email, department_id
                    FROM user_accounts_studentdetails
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (student_id,),
                )
                row = cursor.fetchone()
                if row:
                    return {"status": "ok", "student": _student_record_to_dict(row), "message": f"Found student {row[1]}"}
                return {"status": "not_found", "student": None, "message": f"I couldn't find student {student_id}"}

            if reg_no:
                cursor.execute(
                    "SELECT id, name, reg_no, batch, year, semester, section, email, department_id FROM user_accounts_studentdetails WHERE LOWER(reg_no) = LOWER(%s) LIMIT 10",
                    (str(reg_no).strip(),),
                )
                rows = cursor.fetchall()
                if len(rows) == 1:
                    return {"status": "ok", "student": _student_record_to_dict(rows[0]), "message": f"Found student {rows[0][1]}"}
                if len(rows) > 1:
                    return {"status": "ambiguous", "student": None, "candidates": [_student_record_to_dict(r) for r in rows], "message": f"Found multiple students with registration number {reg_no}"}
                return {"status": "not_found", "student": None, "message": f"I couldn't find registration number {reg_no}"}

            normalized = str(name).strip()
            cursor.execute(
                "SELECT id, name, reg_no, batch, year, semester, section, email, department_id FROM user_accounts_studentdetails WHERE LOWER(name) = LOWER(%s) LIMIT 10",
                (normalized,),
            )
            rows = cursor.fetchall()
            if len(rows) == 1:
                return {"status": "ok", "student": _student_record_to_dict(rows[0]), "message": f"Found student {rows[0][1]}"}
            if len(rows) > 1:
                return {"status": "ambiguous", "student": None, "candidates": [_student_record_to_dict(r) for r in rows], "message": f"Found {len(rows)} students with that name: {', '.join(r[1] for r in rows[:5])}. Please be more specific."}

            cursor.execute(
                "SELECT id, name, reg_no, batch, year, semester, section, email, department_id FROM user_accounts_studentdetails WHERE LOWER(name) LIKE LOWER(%s) LIMIT 10",
                (f"%{normalized}%",),
            )
            rows = cursor.fetchall()
            if len(rows) == 1:
                return {"status": "ok", "student": _student_record_to_dict(rows[0]), "message": f"Found student {rows[0][1]}"}
            if len(rows) > 1:
                return {"status": "ambiguous", "student": None, "candidates": [_student_record_to_dict(r) for r in rows], "message": f"Found {len(rows)} students matching '{name}': {', '.join(r[1] for r in rows[:5])}. Please be more specific."}
            return {"status": "not_found", "student": None, "message": f"I couldn't find a student named {name}"}
        except mariadb.Error as exc:
            return {"status": "error", "student": None, "message": f"Database error while looking up student: {exc}"}
        finally:
            _close_connection(conn)

    conn = _sqlite_connect()
    try:
        if student_id:
            row = conn.execute("SELECT id, name, reg_no, batch, year, semester, section, email, department_id FROM students WHERE id = ? LIMIT 1", (student_id,)).fetchone()
            if row is None:
                return {"status": "not_found", "student": None, "message": f"I couldn't find student {student_id}"}
            return {"status": "ok", "student": dict(row), "message": f"Found student {row['name']}"}

        if reg_no:
            rows = conn.execute("SELECT id, name, reg_no, batch, year, semester, section, email, department_id FROM students WHERE LOWER(reg_no) = LOWER(?) LIMIT 10", (str(reg_no).strip(),)).fetchall()
            if len(rows) == 1:
                return {"status": "ok", "student": dict(rows[0]), "message": f"Found student {rows[0]['name']}"}
            if len(rows) > 1:
                return {"status": "ambiguous", "student": None, "candidates": [dict(r) for r in rows], "message": f"Found multiple students with registration number {reg_no}"}
            return {"status": "not_found", "student": None, "message": f"I couldn't find registration number {reg_no}"}

        normalized = str(name).strip()
        rows = conn.execute("SELECT id, name, reg_no, batch, year, semester, section, email, department_id FROM students WHERE LOWER(name) = LOWER(?) LIMIT 10", (normalized,)).fetchall()
        if len(rows) == 1:
            return {"status": "ok", "student": dict(rows[0]), "message": f"Found student {rows[0]['name']}"}
        if len(rows) > 1:
            return {"status": "ambiguous", "student": None, "candidates": [dict(r) for r in rows], "message": f"Found {len(rows)} students with that name: {', '.join(r['name'] for r in rows)}. Please be more specific."}

        rows = conn.execute("SELECT id, name, reg_no, batch, year, semester, section, email, department_id FROM students WHERE LOWER(name) LIKE LOWER(?) LIMIT 10", (f"%{normalized}%",)).fetchall()
        if len(rows) == 1:
            return {"status": "ok", "student": dict(rows[0]), "message": f"Found student {rows[0]['name']}"}
        if len(rows) > 1:
            return {"status": "ambiguous", "student": None, "candidates": [dict(r) for r in rows], "message": f"Found {len(rows)} students matching '{name}': {', '.join(r['name'] for r in rows)}. Please be more specific."}
        return {"status": "not_found", "student": None, "message": f"I couldn't find a student named {name}"}
    finally:
        _close_connection(conn)


def resolve_student_id(name: str) -> Optional[str]:
    if not name:
        return None
    result = lookup_student(name=name)
    if result["status"] == "ok" and result.get("student"):
        return result["student"]["id"]
    return None


def resolve_student_name(student_id: str) -> Optional[str]:
    if not student_id:
        return None
    result = lookup_student(student_id=student_id)
    if result["status"] == "ok" and result.get("student"):
        return result["student"]["name"]
    return None


def lookup_course(course_code: Optional[str] = None, title: Optional[str] = None) -> Dict[str, Any]:
    if not any([course_code, title]):
        raise ValueError("course_code or title is required")

    if _real_db_enabled():
        conn = None
        try:
            conn = _get_connection()
            cursor = conn.cursor()

            if course_code:
                cursor.execute("SELECT id, course_code, title, year, semester, department_id FROM course_management_course WHERE course_code = %s LIMIT 1", (course_code,))
                row = cursor.fetchone()
                if row:
                    return {"status": "ok", "course": _course_record_to_dict(row), "message": f"Found course {row[2]}"}
                return {"status": "not_found", "course": None, "message": f"I couldn't find course {course_code}"}

            normalized = str(title).strip().lower()
            cursor.execute("SELECT id, course_code, title, year, semester, department_id FROM course_management_course WHERE LOWER(title) = LOWER(%s) LIMIT 10", (normalized,))
            rows = cursor.fetchall()
            if len(rows) == 1:
                return {"status": "ok", "course": _course_record_to_dict(rows[0]), "message": f"Found course {rows[0][2]}"}
            if len(rows) > 1:
                return {"status": "ambiguous", "course": None, "message": f"Found {len(rows)} courses matching '{title}': {', '.join(r[2] for r in rows[:5])}"}

            cursor.execute("SELECT id, course_code, title, year, semester, department_id FROM course_management_course WHERE LOWER(title) LIKE LOWER(%s) LIMIT 10", (f"%{normalized}%",))
            rows = cursor.fetchall()
            if len(rows) == 1:
                return {"status": "ok", "course": _course_record_to_dict(rows[0]), "message": f"Found course {rows[0][2]}"}
            if len(rows) > 1:
                return {"status": "ambiguous", "course": None, "message": f"Found {len(rows)} courses containing '{title}'"}
            return {"status": "not_found", "course": None, "message": f"I couldn't find a course titled {title}"}
        except mariadb.Error as exc:
            return {"status": "error", "course": None, "message": f"Database error while looking up course: {exc}"}
        finally:
            _close_connection(conn)

    conn = _sqlite_connect()
    try:
        if course_code:
            row = conn.execute("SELECT id, course_code, title, year, semester, department_id FROM courses WHERE LOWER(course_code) = LOWER(?) LIMIT 1", (course_code,)).fetchone()
            if row is None:
                return {"status": "not_found", "course": None, "message": f"I couldn't find course {course_code}"}
            return {"status": "ok", "course": dict(row), "message": f"Found course {row['title']}"}

        normalized = str(title).strip().lower()
        rows = conn.execute("SELECT id, course_code, title, year, semester, department_id FROM courses WHERE LOWER(title) = LOWER(?) LIMIT 10", (normalized,)).fetchall()
        if len(rows) == 1:
            return {"status": "ok", "course": dict(rows[0]), "message": f"Found course {rows[0]['title']}"}
        if len(rows) > 1:
            return {"status": "ambiguous", "course": None, "message": f"Found {len(rows)} courses matching '{title}'"}

        rows = conn.execute("SELECT id, course_code, title, year, semester, department_id FROM courses WHERE LOWER(title) LIKE LOWER(?) LIMIT 10", (f"%{normalized}%",)).fetchall()
        if len(rows) == 1:
            return {"status": "ok", "course": dict(rows[0]), "message": f"Found course {rows[0]['title']}"}
        if len(rows) > 1:
            return {"status": "ambiguous", "course": None, "message": f"Found {len(rows)} courses containing '{title}'"}
        return {"status": "not_found", "course": None, "message": f"I couldn't find a course titled {title}"}
    finally:
        _close_connection(conn)


def get_enrollment(student_id: str) -> Dict[str, Any]:
    if not student_id:
        raise ValueError("student_id is required")

    if _real_db_enabled():
        conn = None
        try:
            conn = _get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM user_accounts_studentdetails WHERE id = %s LIMIT 1", (student_id,))
            if cursor.fetchone() is None:
                return {"status": "not_found", "enrollments": [], "message": f"I couldn't find student {student_id}"}
            cursor.execute(
                """
                SELECT ce.id, ce.course_id, ce.enrollment_date, c.course_code, c.title, c.year, c.semester
                FROM course_management_courseenrollment ce
                JOIN course_management_course c ON ce.course_id = c.id
                WHERE ce.student_id = %s
                ORDER BY c.year, c.semester
                """,
                (student_id,),
            )
            rows = cursor.fetchall()
            if not rows:
                return {"status": "no_data", "enrollments": [], "message": f"No course enrollments found for student {student_id}"}
            enrollments = [{"enrollment_id": r[0], "course_id": r[1], "enrollment_date": str(r[2]) if r[2] else None, "course_code": r[3], "course_title": r[4], "year": r[5], "semester": r[6]} for r in rows]
            return {"status": "ok", "enrollments": enrollments, "message": f"Found {len(enrollments)} course enrollment(s) for student {student_id}"}
        except mariadb.Error as exc:
            return {"status": "error", "enrollments": [], "message": f"Database error while looking up enrollments: {exc}"}
        finally:
            _close_connection(conn)

    conn = _sqlite_connect()
    try:
        row = conn.execute("SELECT id FROM students WHERE id = ? LIMIT 1", (student_id,)).fetchone()
        if row is None:
            return {"status": "not_found", "enrollments": [], "message": f"I couldn't find student {student_id}"}
        rows = conn.execute("SELECT id, course_id, enrollment_date, course_code, course_title, year, semester FROM enrollments WHERE student_id = ? ORDER BY year, semester", (student_id,)).fetchall()
        if not rows:
            return {"status": "no_data", "enrollments": [], "message": f"No course enrollments found for student {student_id}"}
        return {"status": "ok", "enrollments": [{"enrollment_id": r["id"], "course_id": r["course_id"], "enrollment_date": r["enrollment_date"], "course_code": r["course_code"], "course_title": r["course_title"], "year": r["year"], "semester": r["semester"]} for r in rows], "message": f"Found {len(rows)} course enrollment(s) for student {student_id}"}
    finally:
        _close_connection(conn)


def get_attendance(student_id: str, subject: Optional[str] = None) -> Dict[str, Any]:
    if not student_id:
        raise ValueError("student_id is required")

    if _real_db_enabled():
        conn = None
        try:
            conn = _get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM user_accounts_studentdetails WHERE id = %s LIMIT 1", (student_id,))
            if cursor.fetchone() is None:
                return {"status": "not_found", "rows": [], "message": f"I couldn't find student {student_id}"}

            cursor.execute(
                """
                SELECT da.id, da.date, da.full_day_status, da.morning_status, da.afternoon_status, da.remarks, c.course_code, c.title
                FROM student_management_daily_attendance da
                LEFT JOIN course_management_course c ON da.course_id = c.id
                WHERE da.student_id = %s
                ORDER BY da.date DESC
                """,
                (student_id,),
            )
            rows = cursor.fetchall()
            if not rows:
                return {"status": "no_data", "rows": [], "message": f"No attendance recorded for student {student_id}"}
            if subject:
                normalized = _normalize_subject(subject)
                rows = [r for r in rows if _normalize_subject(r[6]) == normalized or _normalize_subject(r[7]) == normalized]
                if not rows:
                    return {"status": "no_data", "rows": [], "message": f"No attendance recorded for {subject}"}
            attendance_rows = [{"id": r[0], "date": str(r[1]) if r[1] else None, "status": r[2] or "unmarked", "morning_status": r[3], "afternoon_status": r[4], "remarks": r[5], "course_code": r[6], "course_title": r[7]} for r in rows]
            summary = ", ".join(f"{r['date']}={r['status']}" for r in attendance_rows[:5])
            return {"status": "ok", "rows": attendance_rows, "message": f"Attendance for {subject or 'all courses'}: {summary}{'...' if len(attendance_rows) > 5 else ''}"}
        except mariadb.Error as exc:
            return {"status": "error", "rows": [], "message": f"Database error while reading attendance: {exc}"}
        finally:
            _close_connection(conn)

    conn = _sqlite_connect()
    try:
        row = conn.execute("SELECT id FROM students WHERE id = ? LIMIT 1", (student_id,)).fetchone()
        if row is None:
            return {"status": "not_found", "rows": [], "message": f"I couldn't find student {student_id}"}
        rows = conn.execute("SELECT id, attendance_date, status, subject FROM attendance WHERE student_id = ? ORDER BY attendance_date DESC", (student_id,)).fetchall()
        if not rows:
            return {"status": "no_data", "rows": [], "message": f"No attendance recorded for student {student_id}"}
        if subject:
            rows = [r for r in rows if _normalize_subject(r["subject"]) == _normalize_subject(subject)]
            if not rows:
                return {"status": "no_data", "rows": [], "message": f"No attendance recorded for {subject}"}
        attendance_rows = [{"id": r["id"], "date": r["attendance_date"], "status": r["status"], "morning_status": None, "afternoon_status": None, "remarks": None, "course_code": r["subject"], "course_title": r["subject"]} for r in rows]
        summary = ", ".join(f"{r['date']}={r['status']}" for r in attendance_rows[:5])
        return {"status": "ok", "rows": attendance_rows, "message": f"Attendance for {subject or 'all courses'}: {summary}{'...' if len(attendance_rows) > 5 else ''}"}
    finally:
        _close_connection(conn)


def get_marks(student_id: str, subject: Optional[str] = None) -> Dict[str, Any]:
    if not student_id:
        raise ValueError("student_id is required")

    if _real_db_enabled():
        conn = None
        try:
            conn = _get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, reg_no FROM user_accounts_studentdetails WHERE id = %s LIMIT 1", (student_id,))
            student_row = cursor.fetchone()
            if student_row is None:
                return {"status": "not_found", "rows": [], "message": f"I couldn't find student {student_id}"}
            reg_no = student_row[1]

            cursor.execute(
                """
                SELECT se.id, se.exam_name, se.course_code, se.course_title, se.created_at,
                       COALESCE(SUM(sm.marks_obtained), 0) AS total_marks,
                       COALESCE(SUM(sm.max_marks), 0) AS max_marks
                FROM examination_management_studentexam se
                LEFT JOIN examination_management_studentmark sm ON se.id = sm.student_exam_id
                WHERE se.reg_no = %s
                GROUP BY se.id, se.exam_name, se.course_code, se.course_title, se.created_at
                ORDER BY se.created_at DESC
                """,
                (reg_no,),
            )
            rows = cursor.fetchall()
            if not rows:
                return {"status": "no_data", "rows": [], "message": f"No marks recorded for student {student_id}"}
            if subject:
                normalized = _normalize_subject(subject)
                rows = [r for r in rows if _normalize_subject(r[2]) == normalized or _normalize_subject(r[3]) == normalized]
                if not rows:
                    return {"status": "no_data", "rows": [], "message": f"No marks recorded for {subject}"}
            marks_rows = [{"exam_id": r[0], "exam_name": r[1], "course_code": r[2], "course_title": r[3], "date": str(r[4]) if r[4] else None, "marks_obtained": r[5] or 0, "max_marks": r[6] or 0, "percentage": (r[5] / r[6] * 100) if r[6] and r[5] else 0} for r in rows]
            summary = ", ".join(f"{r['exam_name']}={r['marks_obtained']}/{r['max_marks']}" for r in marks_rows[:5])
            return {"status": "ok", "rows": marks_rows, "message": f"Marks for {subject or 'all courses'}: {summary}{'...' if len(marks_rows) > 5 else ''}"}
        except mariadb.Error as exc:
            return {"status": "error", "rows": [], "message": f"Database error while reading marks: {exc}"}
        finally:
            _close_connection(conn)

    conn = _sqlite_connect()
    try:
        row = conn.execute("SELECT id FROM students WHERE id = ? LIMIT 1", (student_id,)).fetchone()
        if row is None:
            return {"status": "not_found", "rows": [], "message": f"I couldn't find student {student_id}"}
        rows = conn.execute("SELECT id, exam_name, course_code, course_title, date, marks_obtained, max_marks FROM marks WHERE student_id = ? ORDER BY date DESC", (student_id,)).fetchall()
        if not rows:
            return {"status": "no_data", "rows": [], "message": f"No marks recorded for student {student_id}"}
        if subject:
            normalized = _normalize_subject(subject)
            rows = [r for r in rows if _normalize_subject(r["course_code"]) == normalized or _normalize_subject(r["course_title"]) == normalized]
            if not rows:
                return {"status": "no_data", "rows": [], "message": f"No marks recorded for {subject}"}
        marks_rows = [{"exam_id": r["id"], "exam_name": r["exam_name"], "course_code": r["course_code"], "course_title": r["course_title"], "date": r["date"], "marks_obtained": r["marks_obtained"], "max_marks": r["max_marks"], "percentage": (r["marks_obtained"] / r["max_marks"] * 100) if r["max_marks"] and r["marks_obtained"] else 0} for r in rows]
        summary = ", ".join(f"{r['exam_name']}={r['marks_obtained']}/{r['max_marks']}" for r in marks_rows[:5])
        return {"status": "ok", "rows": marks_rows, "message": f"Marks for {subject or 'all courses'}: {summary}{'...' if len(marks_rows) > 5 else ''}"}
    finally:
        _close_connection(conn)


def get_timetable(student_id: str, year: Optional[int] = None, semester: Optional[int] = None) -> Dict[str, Any]:
    if not student_id:
        raise ValueError("student_id is required")

    if _real_db_enabled():
        conn = None
        try:
            conn = _get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT year, semester, section FROM user_accounts_studentdetails WHERE id = %s LIMIT 1", (student_id,))
            row = cursor.fetchone()
            if row is None:
                return {"status": "not_found", "rows": [], "message": f"I couldn't find student {student_id}"}
            student_year, student_semester, student_section = row
            year = year or student_year
            semester = semester or student_semester

            cursor.execute(
                """
                SELECT id, day, section, year, semester, first_period, second_period, third_period, fourth_period, fifth_period,
                       sixth_period, seventh_period, eighth_period, nineth_period, tenth_period
                FROM course_management_periodallocation
                WHERE year = %s AND semester = %s AND section = %s
                ORDER BY FIELD(day, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'), id
                """,
                (year, semester, student_section),
            )
            rows = cursor.fetchall()
            if not rows:
                return {"status": "no_data", "rows": [], "message": f"No timetable found for {student_id} (Year {year}, Semester {semester})"}
            timetable_rows = []
            for row in rows:
                periods = {"period_1": row[5], "period_2": row[6], "period_3": row[7], "period_4": row[8], "period_5": row[9], "period_6": row[10], "period_7": row[11], "period_8": row[12], "period_9": row[13], "period_10": row[14]}
                for period_name, course_id in periods.items():
                    if course_id:
                        timetable_rows.append({"day": row[1], "section": row[2], "year": row[3], "semester": row[4], "period": period_name, "course_id": course_id})
            summary = ", ".join(f"{r['day']} Period {r['period'].split('_')[1]}" for r in timetable_rows[:5])
            return {"status": "ok", "rows": timetable_rows, "message": f"Timetable for {student_id}: {summary}{'...' if len(timetable_rows) > 5 else ''}"}
        except mariadb.Error as exc:
            return {"status": "error", "rows": [], "message": f"Database error while reading timetable: {exc}"}
        finally:
            _close_connection(conn)

    conn = _sqlite_connect()
    try:
        row = conn.execute("SELECT id FROM students WHERE id = ? LIMIT 1", (student_id,)).fetchone()
        if row is None:
            return {"status": "not_found", "rows": [], "message": f"I couldn't find student {student_id}"}
        rows = conn.execute("SELECT id, day, section, year, semester, period, course_id FROM timetable WHERE student_id = ? ORDER BY day", (student_id,)).fetchall()
        if not rows:
            return {"status": "no_data", "rows": [], "message": f"No timetable found for {student_id}"}
        timetable_rows = [{"day": r["day"], "section": r["section"], "year": r["year"], "semester": r["semester"], "period": r["period"], "course_id": r["course_id"]} for r in rows]
        summary = ", ".join(f"{r['day']} Period {r['period'].split('_', 1)[1] if '_' in r['period'] else r['period']}" for r in timetable_rows[:5])
        return {"status": "ok", "rows": timetable_rows, "message": f"Timetable for {student_id}: {summary}{'...' if len(timetable_rows) > 5 else ''}"}
    finally:
        _close_connection(conn)


def mark_attendance(student_id: str, subject: str, date: str, status: str, actor_id: str) -> Dict[str, Any]:
    if not student_id:
        raise ValueError("student_id is required")
    if not subject:
        raise ValueError("subject is required")
    if not date:
        raise ValueError("date is required")
    if not status:
        raise ValueError("status is required")
    if not actor_id:
        raise ValueError("actor_id is required")

    if _real_db_enabled():
        conn = None
        try:
            conn = _get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM user_accounts_studentdetails WHERE id = %s LIMIT 1", (student_id,))
            if cursor.fetchone() is None:
                return {"status": "not_found", "message": f"I couldn't find student {student_id}"}

            cursor.execute("SELECT id, course_code, title FROM course_management_course WHERE course_code = %s OR LOWER(title) LIKE LOWER(%s) LIMIT 1", (subject, f"%{subject}%"))
            course_row = cursor.fetchone()
            if course_row is None:
                return {"status": "not_found", "message": f"I couldn't find course {subject}"}
            course_id = course_row[0]

            cursor.execute("SELECT id, full_day_status FROM student_management_daily_attendance WHERE student_id = %s AND course_id = %s AND date = %s LIMIT 1", (student_id, course_id, date))
            existing_row = cursor.fetchone()
            if existing_row and existing_row[1] and existing_row[1].lower() == status.lower():
                return {"status": "unchanged", "message": f"Attendance already marked as {status}"}
            if existing_row:
                cursor.execute("UPDATE student_management_daily_attendance SET full_day_status = %s WHERE id = %s", (status, existing_row[0]))
                result_status = "updated"
            else:
                cursor.execute("INSERT INTO student_management_daily_attendance (student_id, course_id, date, full_day_status, marked_at) VALUES (%s, %s, %s, %s, NOW())", (student_id, course_id, date, status))
                result_status = "created"
            cursor.execute("INSERT INTO voxerp_write_log (actor_id, action, target_student_id, course_id, attendance_date, status, timestamp) VALUES (%s, %s, %s, %s, %s, %s, NOW())", (actor_id, "mark_attendance", student_id, course_id, date, status))
            conn.commit()
            return {"status": result_status, "message": f"{'Updated' if result_status == 'updated' else 'Marked'} attendance for {student_id} in {subject} on {date} as {status}"}
        except mariadb.Error as exc:
            if conn is not None:
                conn.rollback()
            return {"status": "error", "message": f"Database error while writing attendance: {exc}"}
        finally:
            _close_connection(conn)

    conn = _sqlite_connect()
    try:
        row = conn.execute("SELECT id FROM students WHERE id = ? LIMIT 1", (student_id,)).fetchone()
        if row is None:
            return {"status": "not_found", "message": f"I couldn't find student {student_id}"}
        existing = conn.execute("SELECT id, status FROM attendance WHERE student_id = ? AND LOWER(subject) = LOWER(?) AND attendance_date = ? LIMIT 1", (student_id, subject, date)).fetchone()
        if existing and existing["status"].lower() == status.lower():
            return {"status": "unchanged", "message": f"Attendance already marked as {status}"}
        if existing:
            conn.execute("UPDATE attendance SET status = ? WHERE id = ?", (status, existing["id"]))
            result_status = "updated"
        else:
            conn.execute("INSERT INTO attendance (student_id, subject, attendance_date, status) VALUES (?, ?, ?, ?)", (student_id, subject, date, status))
            result_status = "created"
        write_log_columns = {row[1] for row in conn.execute("PRAGMA table_info(write_log)")}
        if "timestamp" in write_log_columns:
            conn.execute("INSERT INTO write_log (actor, action, target, subject, attendance_date, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", (actor_id, "mark_attendance", student_id, subject, date, status))
        else:
            conn.execute("INSERT INTO write_log (actor, action, target, subject, attendance_date, status) VALUES (?, ?, ?, ?, ?, ?)", (actor_id, "mark_attendance", student_id, subject, date, status))
        conn.commit()
        return {"status": result_status, "message": f"{'Updated' if result_status == 'updated' else 'Marked'} attendance for {student_id} in {subject} on {date} as {status}"}
    finally:
        _close_connection(conn)


def build_schema_map() -> Dict[str, Any]:
    if _real_db_enabled():
        conn = None
        try:
            conn = _get_connection()
            cursor = conn.cursor()
            tables = {}
            for table_name in [
                "user_accounts_studentdetails",
                "course_management_course",
                "course_management_courseenrollment",
                "student_management_daily_attendance",
                "examination_management_studentexam",
                "examination_management_studentmark",
                "course_management_periodallocation",
                "course_management_lab_timetable",
            ]:
                try:
                    cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION", (DB_CONFIG["database"], table_name))
                    tables[table_name] = [row[0] for row in cursor.fetchall()]
                except mariadb.Error:
                    pass
            return {"tables": tables, "description": f"VoxERP schema mapping for {DB_CONFIG['database']} (MariaDB)", "db_host": DB_CONFIG["host"], "db_port": DB_CONFIG["port"], "db_name": DB_CONFIG["database"]}
        except mariadb.Error as exc:
            return {"status": "error", "message": f"Failed to build schema map: {exc}"}
        finally:
            _close_connection(conn)

    conn = _sqlite_connect()
    try:
        tables = {}
        for table_name in ["students", "attendance", "write_log", "courses", "enrollments", "marks", "timetable"]:
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            tables[table_name] = [row[1] for row in rows]
        return {"tables": tables, "description": "VoxERP schema mapping for SQLite mock database", "db_host": "local", "db_port": None, "db_name": _DB_FILE}
    finally:
        _close_connection(conn)


def _connect():
    """Backward-compatible alias for app.py and older callers."""
    return _get_connection()
