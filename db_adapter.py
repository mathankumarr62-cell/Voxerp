import os
import re
import sqlite3
from typing import Any, Dict, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "voxerp.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    conn = _connect()
    try:
        conn.executescript(
            """
            DROP TABLE IF EXISTS write_log;

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

        conn.execute("DELETE FROM students")
        conn.execute("DELETE FROM subjects")
        conn.execute("DELETE FROM attendance")
        conn.execute("DELETE FROM marks")
        conn.execute("DELETE FROM timetable")
        conn.execute("DELETE FROM demo_users")
        conn.execute("DELETE FROM write_log")

        students = [
            ("student-1", "Vijay", "student", "CSE-1"),
            ("student-2", "Priya", "student", "CSE-1"),
            ("student-3", "Asha", "student", "CSE-2"),
            ("student-4", "Rohan", "student", "CSE-2"),
            ("student-5", "Meera", "student", "CSE-3"),
            ("student-6", "Arjun", "student", "CSE-3"),
        ]
        conn.executemany("INSERT INTO students (id, name, role, class_name) VALUES (?, ?, ?, ?)", students)

        subjects = ["DBMS", "Operating Systems", "Computer Networks"]
        conn.executemany("INSERT INTO subjects (name) VALUES (?)", [(s,) for s in subjects])

        attendance_rows = [
            ("student-1", "DBMS", "2026-08-01", "present"),
            ("student-1", "DBMS", "2026-08-02", "absent"),
            ("student-2", "DBMS", "2026-08-01", "present"),
            ("student-2", "DBMS", "2026-08-02", "present"),
            ("student-3", "Operating Systems", "2026-08-01", "present"),
            ("student-4", "Computer Networks", "2026-08-01", "present"),
        ]
        conn.executemany(
            "INSERT INTO attendance (student_id, subject, attendance_date, status) VALUES (?, ?, ?, ?)",
            attendance_rows,
        )

        marks_rows = [
            ("student-1", "DBMS", "Quiz 1", 82.0),
            ("student-1", "DBMS", "Midterm", 74.0),
            ("student-2", "DBMS", "Quiz 1", 90.0),
            ("student-3", "Operating Systems", "Quiz 1", 78.0),
            ("student-4", "Computer Networks", "Quiz 1", 88.0),
        ]
        conn.executemany(
            "INSERT INTO marks (student_id, subject, exam_name, score) VALUES (?, ?, ?, ?)",
            marks_rows,
        )

        timetable_rows = [
            ("student-1", "Monday", "DBMS", "09:00-10:00"),
            ("student-1", "Tuesday", "Operating Systems", "11:00-12:00"),
            ("student-2", "Monday", "DBMS", "09:00-10:00"),
            ("student-3", "Tuesday", "Operating Systems", "11:00-12:00"),
        ]
        conn.executemany(
            "INSERT INTO timetable (student_id, day, subject, slot) VALUES (?, ?, ?, ?)",
            timetable_rows,
        )

        demo_users = [
            ("student-1", "student", "Vijay"),
            ("student-2", "student", "Priya"),
            ("teacher-1", "teacher", "Ms. Rao"),
        ]
        conn.executemany("INSERT INTO demo_users (id, role, name) VALUES (?, ?, ?)", demo_users)

        conn.commit()
    finally:
        conn.close()


def _normalize_subject(subject: Optional[str]) -> Optional[str]:
    if subject is None:
        return None
    return re.sub(r"\s+", "", subject).lower()


def _student_exists(conn: sqlite3.Connection, student_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone()
    return row is not None


def _subject_exists(conn: sqlite3.Connection, subject: str) -> bool:
    normalized = _normalize_subject(subject)
    if not normalized:
        return False
    row = conn.execute("SELECT 1 FROM subjects WHERE lower(replace(name, ' ', '')) = ?", (normalized,)).fetchone()
    return row is not None


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
            "SELECT attendance_date, status FROM attendance WHERE student_id = ? AND lower(replace(subject, ' ', '')) = ? ORDER BY attendance_date",
            (student_id, normalized_subject),
        ).fetchall()

        if not rows:
            if _subject_exists(conn, subject):
                return {"status": "no_data", "message": f"No attendance recorded for {subject}"}
            return {"status": "not_found", "message": f"I couldn't find subject {subject}"}

        row_payloads = [{"date": row["attendance_date"], "status": row["status"]} for row in rows]
        summary_parts = [f"{row['date']}={row['status']}" for row in row_payloads]
        return {
            "status": "ok",
            "rows": row_payloads,
            "message": f"Attendance for {subject}: {', '.join(summary_parts)}",
        }
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
            "SELECT exam_name, score FROM marks WHERE student_id = ? AND lower(replace(subject, ' ', '')) = ? ORDER BY exam_name",
            (student_id, normalized_subject),
        ).fetchall()

        if not rows:
            if _subject_exists(conn, subject):
                return {"status": "no_data", "message": f"No marks recorded for {subject}"}
            return {"status": "not_found", "message": f"I couldn't find subject {subject}"}

        row_payloads = [{"exam_name": row["exam_name"], "score": row["score"]} for row in rows]
        summary_parts = [f"{row['exam_name']}={row['score']}" for row in row_payloads]
        return {
            "status": "ok",
            "rows": row_payloads,
            "message": f"Marks for {subject}: {', '.join(summary_parts)}",
        }
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
            "SELECT id, status FROM attendance WHERE student_id = ? AND lower(replace(subject, ' ', '')) = ? AND attendance_date = ?",
            (student_id, normalized_subject, date),
        ).fetchone()

        if existing_row is not None:
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
