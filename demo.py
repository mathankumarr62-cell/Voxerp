from db_adapter import build_schema_map, get_attendance, get_marks, get_timetable, initialize_database, mark_attendance


if __name__ == "__main__":
    initialize_database()
    print("Attendance:", get_attendance("student-1", "dbms"))
    print("Marks:", get_marks("student-1", "DBMS"))
    print("Timetable:", get_timetable("student-1"))
    print("Write:", mark_attendance("student-1", "dbms", "2026-08-07", "present", "teacher-1"))
    print("Schema map:", build_schema_map())
