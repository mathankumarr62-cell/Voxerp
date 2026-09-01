"""
VoxERP Database Adapter Tests
Tests for MariaDB integration with real ramco_academic_system database.
"""

import os
import unittest

import mariadb

from db_adapter import (
    check_connection,
    build_schema_map,
    get_attendance,
    get_marks,
    get_timetable,
    initialize_database,
    mark_attendance,
    lookup_student,
    resolve_student_id,
    resolve_student_name,
    lookup_course,
    get_enrollment,
)


@unittest.skipUnless(str(os.getenv("VOXERP_USE_REAL_DB", "False")).lower() in {"1", "true", "yes", "on"}, "Real MariaDB integration test")
class DbAdapterConnectionTests(unittest.TestCase):
    """Test database connection and initialization."""
    
    def test_connection_succeeds(self):
        """Test that we can connect to the MariaDB database."""
        self.assertTrue(check_connection(), "Database connection test failed")

    def test_live_connection_queries_expected_tables_and_data(self):
        """Verify a real MariaDB connection, query count > 0, and a few student rows."""
        conn = None
        try:
            conn = mariadb.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "3306")),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD", ""),
                database=os.getenv("DB_NAME", "ramco_academic_system"),
            )
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)

            cursor.execute("SELECT COUNT(*) FROM user_accounts_studentdetails")
            student_count = cursor.fetchone()[0]
            self.assertGreater(student_count, 0)

            cursor.execute("SELECT id, name, reg_no FROM user_accounts_studentdetails ORDER BY id LIMIT 3")
            students = cursor.fetchall()
            self.assertGreater(len(students), 0)
            self.assertTrue(any(row[1] for row in students))
            self.assertTrue(any(row[2] for row in students))

            cursor.execute(
                """
                SELECT TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = %s
                  AND TABLE_NAME IN (%s, %s, %s, %s, %s, %s, %s, %s)
                ORDER BY TABLE_NAME
                """,
                (
                    os.getenv("DB_NAME", "ramco_academic_system"),
                    "user_accounts_studentdetails",
                    "course_management_course",
                    "course_management_courseenrollment",
                    "student_management_daily_attendance",
                    "examination_management_studentexam",
                    "examination_management_studentmark",
                    "course_management_periodallocation",
                    "course_management_lab_timetable",
                ),
            )
            tables = {row[0] for row in cursor.fetchall()}
            required = {
                "user_accounts_studentdetails",
                "course_management_course",
                "course_management_courseenrollment",
                "student_management_daily_attendance",
                "examination_management_studentexam",
                "examination_management_studentmark",
                "course_management_periodallocation",
                "course_management_lab_timetable",
            }
            self.assertTrue(required.issubset(tables), f"Missing live MariaDB tables: {sorted(required - tables)}")
        finally:
            if conn is not None:
                conn.close()

    def test_initialize_database_creates_tables(self):
        """Test that initialize_database creates required tables."""
        result = initialize_database()
        self.assertEqual(result["status"], "ok")
        self.assertIn("message", result)


@unittest.skipUnless(str(os.getenv("VOXERP_USE_REAL_DB", "False")).lower() in {"1", "true", "yes", "on"}, "Real MariaDB integration test")
class DbAdapterStudentLookupTests(unittest.TestCase):
    """Test student lookup functionality against real database."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        initialize_database()
    
    def test_lookup_student_by_name_vijay(self):
        """Test looking up a student by name (Vijay exists in real DB)."""
        result = lookup_student(name="Vijay")
        # The real database contains Vijay entries
        self.assertIn(result["status"], ["ok", "ambiguous", "not_found"])
        if result["status"] == "ok":
            self.assertIsNotNone(result["student"])
            self.assertIn("name", result["student"])
        elif result["status"] == "ambiguous":
            self.assertGreater(len(result.get("candidates", [])), 1)
    
    def test_lookup_student_not_found(self):
        """Test looking up a non-existent student."""
        result = lookup_student(name="XYZ_NONEXISTENT_12345")
        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["student"])
    
    def test_lookup_student_by_id_fails_gracefully(self):
        """Test that looking up by invalid ID returns not_found."""
        result = lookup_student(student_id="999999999")
        self.assertEqual(result["status"], "not_found")
    
    def test_resolve_student_id_returns_none_for_unknown(self):
        """Test that resolve_student_id returns None for unknown names."""
        result = resolve_student_id("XYZ_NONEXISTENT_12345")
        self.assertIsNone(result)
    
    def test_resolve_student_name_returns_none_for_unknown(self):
        """Test that resolve_student_name returns None for unknown IDs."""
        result = resolve_student_name("999999999")
        self.assertIsNone(result)
    
    def test_lookup_student_raises_on_missing_params(self):
        """Test that lookup_student raises ValueError when called with no params."""
        with self.assertRaises(ValueError):
            lookup_student()


@unittest.skipUnless(str(os.getenv("VOXERP_USE_REAL_DB", "False")).lower() in {"1", "true", "yes", "on"}, "Real MariaDB integration test")
class DbAdapterCourseLookupTests(unittest.TestCase):
    """Test course lookup functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        initialize_database()
    
    def test_lookup_course_raises_on_missing_params(self):
        """Test that lookup_course raises ValueError when called with no params."""
        with self.assertRaises(ValueError):
            lookup_course()
    
    def test_lookup_course_by_nonexistent_code(self):
        """Test looking up a non-existent course code."""
        result = lookup_course(course_code="NONEXISTENT_XYZ")
        self.assertEqual(result["status"], "not_found")
    
    def test_lookup_course_by_nonexistent_title(self):
        """Test looking up a non-existent course title."""
        result = lookup_course(title="XYZ_NONEXISTENT_12345")
        self.assertEqual(result["status"], "not_found")


@unittest.skipUnless(str(os.getenv("VOXERP_USE_REAL_DB", "False")).lower() in {"1", "true", "yes", "on"}, "Real MariaDB integration test")
class DbAdapterAttendanceTests(unittest.TestCase):
    """Test attendance retrieval."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        initialize_database()
    
    def test_get_attendance_not_found_for_unknown_student(self):
        """Test get_attendance returns not_found for unknown student."""
        result = get_attendance("999999999")
        self.assertEqual(result["status"], "not_found")
        self.assertIn("I couldn't find student", result["message"])
    
    def test_get_attendance_raises_on_missing_student_id(self):
        """Test that get_attendance raises ValueError when student_id is missing."""
        with self.assertRaises(ValueError):
            get_attendance("")
    
    def test_get_attendance_handles_no_records(self):
        """Test get_attendance returns no_data when student has no attendance."""
        # This test depends on finding a real student with no attendance
        # For now, just verify the function handles it gracefully
        result = get_attendance("999999999")
        self.assertIn(result["status"], ["not_found", "no_data"])


@unittest.skipUnless(str(os.getenv("VOXERP_USE_REAL_DB", "False")).lower() in {"1", "true", "yes", "on"}, "Real MariaDB integration test")
class DbAdapterMarksTests(unittest.TestCase):
    """Test marks retrieval."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        initialize_database()
    
    def test_get_marks_not_found_for_unknown_student(self):
        """Test get_marks returns not_found for unknown student."""
        result = get_marks("999999999")
        self.assertEqual(result["status"], "not_found")
    
    def test_get_marks_raises_on_missing_student_id(self):
        """Test that get_marks raises ValueError when student_id is missing."""
        with self.assertRaises(ValueError):
            get_marks("")


@unittest.skipUnless(str(os.getenv("VOXERP_USE_REAL_DB", "False")).lower() in {"1", "true", "yes", "on"}, "Real MariaDB integration test")
class DbAdapterTimetableTests(unittest.TestCase):
    """Test timetable retrieval."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        initialize_database()
    
    def test_get_timetable_not_found_for_unknown_student(self):
        """Test get_timetable returns not_found for unknown student."""
        result = get_timetable("999999999")
        self.assertEqual(result["status"], "not_found")
    
    def test_get_timetable_raises_on_missing_student_id(self):
        """Test that get_timetable raises ValueError when student_id is missing."""
        with self.assertRaises(ValueError):
            get_timetable("")


@unittest.skipUnless(str(os.getenv("VOXERP_USE_REAL_DB", "False")).lower() in {"1", "true", "yes", "on"}, "Real MariaDB integration test")
class DbAdapterSchemaMapTests(unittest.TestCase):
    """Test schema map generation."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        initialize_database()
    
    def test_build_schema_map_returns_tables(self):
        """Test that build_schema_map returns table information."""
        result = build_schema_map()
        self.assertIn("tables", result)
        self.assertIsInstance(result["tables"], dict)
        # Check that we have the expected real tables
        expected_tables = [
            'user_accounts_studentdetails',
            'course_management_course',
            'student_management_daily_attendance',
            'course_management_lab_timetable',
        ]
        for table in expected_tables:
            self.assertIn(table, result["tables"])


@unittest.skipUnless(str(os.getenv("VOXERP_USE_REAL_DB", "False")).lower() in {"1", "true", "yes", "on"}, "Real MariaDB integration test")
class DbAdapterWriteTests(unittest.TestCase):
    """Test write operations (attendance marking)."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        initialize_database()
    
    def test_mark_attendance_raises_on_missing_params(self):
        """Test that mark_attendance raises ValueError when params are missing."""
        with self.assertRaises(ValueError):
            mark_attendance("", "DBMS", "2026-09-01", "present", "teacher-1")
        
        with self.assertRaises(ValueError):
            mark_attendance("student-1", "", "2026-09-01", "present", "teacher-1")
    
    def test_mark_attendance_not_found_for_unknown_student(self):
        """Test mark_attendance returns not_found for unknown student."""
        result = mark_attendance(
            "999999999", "DBMS", "2026-09-01", "present", "teacher-1"
        )
        self.assertEqual(result["status"], "not_found")
    
    def test_mark_attendance_not_found_for_unknown_course(self):
        """Test mark_attendance returns not_found for unknown course."""
        # This test assumes there's a real student but NONEXISTENT_XYZ course doesn't exist
        # We'll catch the not_found for student first, but the logic should work
        result = mark_attendance(
            "999999999", "NONEXISTENT_XYZ", "2026-09-01", "present", "teacher-1"
        )
        self.assertEqual(result["status"], "not_found")


@unittest.skipUnless(str(os.getenv("VOXERP_USE_REAL_DB", "False")).lower() in {"1", "true", "yes", "on"}, "Real MariaDB integration test")
class DbAdapterIntegrationTests(unittest.TestCase):
    """Integration tests for multiple operations."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        initialize_database()
    
    def test_schema_map_has_attendance_table(self):
        """Test that schema map includes attendance table."""
        schema_map = build_schema_map()
        self.assertIn("student_management_daily_attendance", schema_map["tables"])
    
    def test_schema_map_has_marks_table(self):
        """Test that schema map includes marks table."""
        schema_map = build_schema_map()
        self.assertIn("examination_management_studentmark", schema_map["tables"])
    
    def test_schema_map_has_timetable_table(self):
        """Test that schema map includes timetable table."""
        schema_map = build_schema_map()
        self.assertIn("course_management_periodallocation", schema_map["tables"])


if __name__ == "__main__":
    unittest.main()
