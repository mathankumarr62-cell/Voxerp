import os
import sqlite3
import tempfile
import unittest
import warnings

import db_adapter
from db_adapter import (
    build_schema_map,
    get_attendance,
    get_marks,
    get_timetable,
    initialize_database,
    mark_attendance,
)


@unittest.skipUnless(str(os.getenv("VOXERP_USE_REAL_DB", "False")).lower() in {"0", "false", "no", "off", ""}, "SQLite mock-mode unit tests")
class DbAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._original_db_file = db_adapter._DB_FILE
        temp_db = tempfile.NamedTemporaryFile(prefix="voxerp-test-", suffix=".db", delete=False)
        cls._test_db_file = temp_db.name
        temp_db.close()
        os.unlink(cls._test_db_file)
        db_adapter._DB_FILE = cls._test_db_file
        initialize_database()

    def setUp(self):
        conn = sqlite3.connect(self._test_db_file)
        try:
            conn.execute(
                "DELETE FROM attendance WHERE student_id = ? AND subject = ? AND attendance_date = ?",
                ("student-1", "DBMS", "2026-08-20"),
            )
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def tearDownClass(cls):
        db_adapter._DB_FILE = cls._original_db_file
        if os.path.exists(cls._test_db_file):
            os.unlink(cls._test_db_file)

    def test_attendance_not_found_for_unknown_student(self):
        result = get_attendance("student-404", "dbms")
        self.assertEqual(result["status"], "not_found")
        self.assertIn("student", result["message"].lower())

    def test_attendance_no_data_for_student_without_records(self):
        result = get_attendance("student-6", "dbms")
        self.assertEqual(result["status"], "no_data")
        self.assertIn("no attendance", result["message"].lower())

    def test_subject_name_is_normalized(self):
        result = get_marks("student-1", "  DBMS  ")
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(len(result["rows"]), 1)

    def test_initialize_database_preserves_existing_data(self):
        conn = sqlite3.connect(db_adapter._DB_FILE)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO students (id, name, role, class_name) VALUES (?, ?, ?, ?)",
                ("custom-99", "Custom Student", "student", "CSE-9"),
            )
            conn.commit()
        finally:
            conn.close()

        initialize_database()

        conn = sqlite3.connect(db_adapter._DB_FILE)
        try:
            row = conn.execute(
                "SELECT name FROM students WHERE id = ?",
                ("custom-99",),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "Custom Student")
        finally:
            conn.execute("DELETE FROM students WHERE id = ?", ("custom-99",))
            conn.commit()
            conn.close()

    def test_connections_are_closed_without_resource_warnings(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            get_attendance("student-1", "dbms")
            get_marks("student-1", "dbms")
            get_timetable("student-1")
            build_schema_map()

        self.assertEqual([warning for warning in caught if warning.category is ResourceWarning], [])

    def test_mark_attendance_is_idempotent_and_logs_once(self):
        date = "2026-08-20"
        result = mark_attendance("student-1", "dbms", date, "present", "teacher-1")
        self.assertEqual(result["status"], "created")

        duplicate = mark_attendance("student-1", "dbms", date, "present", "teacher-1")
        self.assertEqual(duplicate["status"], "unchanged")

        conn = sqlite3.connect(db_adapter._DB_FILE)
        try:
            row_count = conn.execute(
                "SELECT COUNT(*) FROM attendance WHERE student_id = ? AND attendance_date = ? AND lower(replace(subject, ' ', '')) = ?",
                ("student-1", date, "dbms"),
            ).fetchone()[0]
            log_count = conn.execute(
                "SELECT COUNT(*) FROM write_log WHERE actor = ? AND action = 'mark_attendance' AND target = ? AND attendance_date = ?",
                ("teacher-1", "student-1", date),
            ).fetchone()[0]
        finally:
            conn.close()

        self.assertEqual(row_count, 1)
        self.assertEqual(log_count, 1)

    def test_mark_attendance_updates_existing_status_without_duplicate_row(self):
        date = "2026-08-21"
        mark_attendance("student-2", "DBMS", date, "present", "teacher-1")
        updated = mark_attendance("student-2", "DBMS", date, "absent", "teacher-1")

        self.assertEqual(updated["status"], "updated")

        conn = sqlite3.connect(db_adapter._DB_FILE)
        try:
            rows = conn.execute(
                "SELECT status FROM attendance WHERE student_id = ? AND attendance_date = ? AND lower(replace(subject, ' ', '')) = ?",
                ("student-2", date, "dbms"),
            ).fetchall()
            log_count = conn.execute(
                "SELECT COUNT(*) FROM write_log WHERE actor = ? AND target = ? AND attendance_date = ?",
                ("teacher-1", "student-2", date),
            ).fetchone()[0]
        finally:
            conn.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "absent")
        self.assertGreaterEqual(log_count, 2)

    def test_write_log_uses_actor_id_not_student_id(self):
        date = "2026-08-22"
        mark_attendance("student-1", "DBMS", date, "present", "teacher-1")

        conn = sqlite3.connect(db_adapter._DB_FILE)
        try:
            row = conn.execute(
                "SELECT actor, target FROM write_log WHERE target = ? AND attendance_date = ? ORDER BY id DESC LIMIT 1",
                ("student-1", date),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row[0], "teacher-1")
        self.assertEqual(row[1], "student-1")

    def test_write_log_records_subject_date_and_status(self):
        date = "2026-08-23"
        mark_attendance("student-1", "DBMS", date, "absent", "teacher-1")

        conn = sqlite3.connect(db_adapter._DB_FILE)
        try:
            row = conn.execute(
                "SELECT subject, attendance_date, status FROM write_log WHERE target = ? AND action = 'mark_attendance' AND attendance_date = ? ORDER BY id DESC LIMIT 1",
                ("student-1", date),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row[0], "DBMS")
        self.assertEqual(row[1], date)
        self.assertEqual(row[2], "absent")

    def test_missing_required_field_raises_clear_error(self):
        with self.assertRaises(ValueError):
            mark_attendance("student-1", None, "2026-08-07", "present", "teacher-1")

    def test_mark_attendance_requires_actor_id(self):
        with self.assertRaises(ValueError):
            mark_attendance("student-1", "dbms", "2026-08-07", "present", "")

    def test_schema_map_contains_expected_tables(self):
        schema_map = build_schema_map()
        self.assertIn("students", schema_map["tables"])
        self.assertIn("attendance", schema_map["tables"])


if __name__ == "__main__":
    unittest.main()
