import os
import re
import sqlite3
from typing import Any, Dict, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "voxerp.db")

SUBJECT_ALIASES = {
    "dbms": {"dbms", "database management systems", "database-management-systems", "database_management_systems"},
    "operatingsystems": {"operating systems", "operating-systems", "operating_systems", "os"},
    "computernetworks": {"computer networks", "computer-networks", "computer_networks", "cn"},
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_subject(subject: Optional[str]) -> Optional[str]:
    if subject is None:
        return None

    text = str(subject).strip().lower()
    compact = re.sub(r"[^a-z0-9]+", "", text)
    if not compact:
        return None

    for canonical, aliases in SUBJECT_ALIASES.items():
        alias_values = {re.sub(r"[^a-z0-9]+", "", alias.lower()) for alias in aliases}
        if compact in alias_values:
            return canonical
    return compact


def _student_exists(conn: sqlite3.Connection, student_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone()
    return row is not None


def _subject_exists(conn: sqlite3.Connection, subject: str) -> bool:
    normalized = _normalize_subject(subject)
    if not normalized:
        return False

    rows = conn.execute("SELECT name FROM subjects").fetchall()
    for row in rows:
        if _normalize_subject(row["name"]) == normalized:
            return True
    return False


def _resolve_student_record(conn: sqlite3.Connection, student_id: Optional[str] = None, name: Optional[str] = None) -> Optional[sqlite3.Row]:
    if student_id:
        return conn.execute(
            "SELECT id, name, role, class_name FROM students WHERE id = ?",
            (student_id,),
        ).fetchone()

    if name:
        normalized_name = str(name).strip()
        if not normalized_name:
            return None
        return conn.execute(
            "SELECT id, name, role, class_name FROM students WHERE lower(name) = lower(?)",
            (normalized_name,),
        ).fetchone()

    return None


def initialize_database() -> None:
    conn = _connect()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                class_name TEXT
            );

            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                attendance_date TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id)
            );

            CREATE TABLE IF NOT EXISTS marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                exam_name TEXT NOT NULL,
                score REAL NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id)
            );

            CREATE TABLE IF NOT EXISTS timetable (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                day TEXT NOT NULL,
                subject TEXT NOT NULL,
                slot TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id)
            );

            CREATE TABLE IF NOT EXISTS demo_users (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS write_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                subject TEXT NOT NULL,
                attendance_date TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            """
        )

        if conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
            students = [
                ("student-1", "Vijay", "student", "CSE-1"),
                ("student-2", "Priya", "student", "CSE-1"),
                ("student-3", "Asha", "student", "CSE-2"),
                ("student-4", "Rohan", "student", "CSE-2"),
                ("student-5", "Meera", "student", "CSE-3"),
                ("student-6", "Arjun", "student", "CSE-3"),
            ]
            conn.executemany("INSERT INTO students (id, name, role, class_name) VALUES (?, ?, ?, ?)", students)

        if conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0] == 0:
            subjects = ["DBMS", "Operating Systems", "Computer Networks"]
            conn.executemany("INSERT OR IGNORE INTO subjects (name) VALUES (?)", [(s,) for s in subjects])

        if conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0] == 0:
            attendance_rows = [
                ("student-1", "DBMS", "2026-08-01", "present"),
                ("student-1", "DBMS", "2026-08-02", "absent"),
                ("student-2", "DBMS", "2026-08-01", "present"),
                ("student-2", "DBMS", "2026-08-02", "present"),
                ("student-3", "Operating Systems", "2026-08-01", "present"),
                ("student-4", "Computer Networks", "2026-08-01", "present"),
            ]
            conn.executemany(
                "INSERT OR IGNORE INTO attendance (student_id, subject, attendance_date, status) VALUES (?, ?, ?, ?)",
                attendance_rows,
            )

        if conn.execute("SELECT COUNT(*) FROM marks").fetchone()[0] == 0:
            marks_rows = [
                ("student-1", "DBMS", "Quiz 1", 82.0),
                ("student-1", "DBMS", "Midterm", 74.0),
                ("student-2", "DBMS", "Quiz 1", 90.0),
                ("student-3", "Operating Systems", "Quiz 1", 78.0),
                ("student-4", "Computer Networks", "Quiz 1", 88.0),
            ]
            conn.executemany(
                "INSERT OR IGNORE INTO marks (student_id, subject, exam_name, score) VALUES (?, ?, ?, ?)",
                marks_rows,
            )

        if conn.execute("SELECT COUNT(*) FROM timetable").fetchone()[0] == 0:
            timetable_rows = [
                ("student-1", "Monday", "DBMS", "09:00-10:00"),
                ("student-1", "Tuesday", "Operating Systems", "11:00-12:00"),
                ("student-2", "Monday", "DBMS", "09:00-10:00"),
                ("student-3", "Tuesday", "Operating Systems", "11:00-12:00"),
            ]
            conn.executemany(
                "INSERT OR IGNORE INTO timetable (student_id, day, subject, slot) VALUES (?, ?, ?, ?)",
                timetable_rows,
            )

        if conn.execute("SELECT COUNT(*) FROM demo_users").fetchone()[0] == 0:
            demo_users = [
                ("student-1", "student", "Vijay"),
                ("student-2", "student", "Priya"),
                ("teacher-1", "teacher", "Ms. Rao"),
            ]
            conn.executemany("INSERT OR IGNORE INTO demo_users (id, role, name) VALUES (?, ?, ?)", demo_users)

        conn.commit()
    finally:
        conn.close()


def lookup_student(student_id: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
    if not student_id and not name:
        raise ValueError("student_id or name is required")

    conn = _connect()
    try:
        row = _resolve_student_record(conn, student_id=student_id, name=name)
        if row is None:
            lookup_value = student_id or name
            return {"status": "not_found", "message": f"I couldn't find student {lookup_value}"}

        return {
            "status": "ok",
            "student": {
                "id": row["id"],
                "name": row["name"],
                "role": row["role"],
                "class_name": row["class_name"],
            },
            "message": f"Found student {row['name']}",
        }
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        return {"status": "error", "message": f"Database error while looking up student: {exc}"}
    finally:
        conn.close()


def resolve_student_id(name: str) -> Optional[str]:
    if not name:
        return None
    conn = _connect()
    try:
        row = _resolve_student_record(conn, name=name)
        return row["id"] if row is not None else None
    finally:
        conn.close()


def resolve_student_name(student_id: str) -> Optional[str]:
    if not student_id:
        return None
    conn = _connect()
    try:
        row = _resolve_student_record(conn, student_id=student_id)
        return row["name"] if row is not None else None
    finally:
        conn.close()


def lookup_subject(subject: str) -> Dict[str, Any]:
    if not subject:
        raise ValueError("subject is required")

    normalized = _normalize_subject(subject)
    if not normalized:
        return {"status": "not_found", "message": "I couldn't find that subject"}

    conn = _connect()
    try:
        rows = conn.execute("SELECT id, name FROM subjects").fetchall()
        for row in rows:
            if _normalize_subject(row["name"]) == normalized:
                return {"status": "ok", "subject": {"id": row["id"], "name": row["name"]}, "message": f"Found subject {row['name']}"}
        return {"status": "not_found", "message": f"I couldn't find subject {subject}"}
    except sqlite3.Error as exc:
        return {"status": "error", "message": f"Database error while looking up subject: {exc}"}
    finally:
        conn.close()


def get_attendance(student_id: str, subject: str) -> Dict[str, Any]:
    if not student_id:
        raise ValueError("student_id is required")
    if not subject:
        raise ValueError("subject is required")

    conn = _connect()
    try:
        if not _student_exists(conn, student_id):
            return {"status": "not_found", "message": f"I couldn't find student {student_id}"}

        normalized_subject = _normalize_subject(subject)
        if not normalized_subject:
            return {"status": "not_found", "message": "I couldn't find that subject"}

        rows = conn.execute(
            "SELECT attendance_date, status, subject FROM attendance WHERE student_id = ? ORDER BY attendance_date",
            (student_id,),
        ).fetchall()
        matched_rows = [
            row for row in rows if _normalize_subject(row["subject"]) == normalized_subject
        ]

        if not matched_rows:
            if _subject_exists(conn, subject):
                return {"status": "no_data", "message": f"No attendance recorded for {subject}"}
            return {"status": "not_found", "message": f"I couldn't find subject {subject}"}

        row_payloads = [{"date": row["attendance_date"], "status": row["status"]} for row in matched_rows]
        summary_parts = [f"{row['date']}={row['status']}" for row in row_payloads]
        return {
            "status": "ok",
            "rows": row_payloads,
            "message": f"Attendance for {subject}: {', '.join(summary_parts)}",
        }
    except sqlite3.Error as exc:
        return {"status": "error", "message": f"Database error while reading attendance: {exc}"}
    finally:
        conn.close()


def get_marks(student_id: str, subject: str) -> Dict[str, Any]:
    if not student_id:
        raise ValueError("student_id is required")
    if not subject:
        raise ValueError("subject is required")

    conn = _connect()
    try:
        if not _student_exists(conn, student_id):
            return {"status": "not_found", "message": f"I couldn't find student {student_id}"}

        normalized_subject = _normalize_subject(subject)
        if not normalized_subject:
            return {"status": "not_found", "message": "I couldn't find that subject"}

        rows = conn.execute(
            "SELECT exam_name, score, subject FROM marks WHERE student_id = ? ORDER BY exam_name",
            (student_id,),
        ).fetchall()
        matched_rows = [row for row in rows if _normalize_subject(row["subject"]) == normalized_subject]

        if not matched_rows:
            if _subject_exists(conn, subject):
                return {"status": "no_data", "message": f"No marks recorded for {subject}"}
            return {"status": "not_found", "message": f"I couldn't find subject {subject}"}

        row_payloads = [{"exam_name": row["exam_name"], "score": row["score"]} for row in matched_rows]
        summary_parts = [f"{row['exam_name']}={row['score']}" for row in row_payloads]
        return {
            "status": "ok",
            "rows": row_payloads,
            "message": f"Marks for {subject}: {', '.join(summary_parts)}",
        }
    except sqlite3.Error as exc:
        return {"status": "error", "message": f"Database error while reading marks: {exc}"}
    finally:
        conn.close()


def get_timetable(student_id: str) -> Dict[str, Any]:
    if not student_id:
        raise ValueError("student_id is required")

    conn = _connect()
    try:
        if not _student_exists(conn, student_id):
            return {"status": "not_found", "message": f"I couldn't find student {student_id}"}

        rows = conn.execute(
            "SELECT day, subject, slot FROM timetable WHERE student_id = ? ORDER BY day, slot",
            (student_id,),
        ).fetchall()

        if not rows:
            return {"status": "no_data", "message": f"No timetable found for {student_id}"}

        row_payloads = [{"day": row["day"], "subject": row["subject"], "slot": row["slot"]} for row in rows]
        summary_parts = [f"{row['day']} {row['subject']} {row['slot']}" for row in row_payloads]
        return {
            "status": "ok",
            "rows": row_payloads,
            "message": f"Timetable for {student_id}: {', '.join(summary_parts)}",
        }
    except sqlite3.Error as exc:
        return {"status": "error", "message": f"Database error while reading timetable: {exc}"}
    finally:
        conn.close()


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

    normalized_subject = _normalize_subject(subject)
    if not normalized_subject:
        raise ValueError("subject is required")

    conn = _connect()
    try:
        if not _student_exists(conn, student_id):
            return {"status": "not_found", "message": f"I couldn't find student {student_id}"}

        if not _subject_exists(conn, subject):
            return {"status": "not_found", "message": f"I couldn't find subject {subject}"}

        existing_row = conn.execute(
            "SELECT id, status, subject FROM attendance WHERE student_id = ? AND attendance_date = ? ORDER BY id",
            (student_id, date),
        ).fetchone()

        if existing_row is not None:
            if _normalize_subject(existing_row["subject"]) == normalized_subject:
                if existing_row["status"].lower() == status.lower():
                    return {"status": "unchanged", "message": f"Attendance already marked as {status}"}

                conn.execute(
                    "UPDATE attendance SET status = ? WHERE id = ?",
                    (status, existing_row["id"]),
                )
                conn.execute(
                    "INSERT INTO write_log (actor, action, target, subject, attendance_date, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
                    (actor_id, "mark_attendance", student_id, subject, date, status),
                )
                conn.commit()
                return {"status": "updated", "message": f"Updated attendance for {student_id} in {subject} on {date} to {status}"}

        conn.execute(
            "INSERT INTO attendance (student_id, subject, attendance_date, status) VALUES (?, ?, ?, ?)",
            (student_id, subject, date, status),
        )
        conn.execute(
            "INSERT INTO write_log (actor, action, target, subject, attendance_date, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (actor_id, "mark_attendance", student_id, subject, date, status),
        )
        conn.commit()

        return {"status": "created", "message": f"Marked attendance for {student_id} in {subject} on {date} as {status}"}
    except sqlite3.Error as exc:
        return {"status": "error", "message": f"Database error while writing attendance: {exc}"}
    finally:
        conn.close()


def build_schema_map() -> Dict[str, Any]:
    conn = _connect()
    try:
        tables = {}
        for table_name in ["students", "subjects", "attendance", "marks", "timetable", "demo_users", "write_log"]:
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")]
            tables[table_name] = columns

        return {
            "tables": tables,
            "description": "Mock ERP schema for students, subjects, attendance, marks, timetable, demo user selection, and write logging.",
        }
    finally:
        conn.close()
