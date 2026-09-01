# VoxERP Database Schema Mapping

## Overview

VoxERP now uses the real **ramco_academic_system** MariaDB database as its source of truth instead of SQLite mock data. This document maps VoxERP's logical entities to the actual database tables and explains how to query them.

**Database:** `ramco_academic_system` (MariaDB 12.3.3)  
**Location:** `localhost:3306`

---

## Schema Mapping

### 1. Students

**Logical Entity:** Student  
**Real Table:** `user_accounts_studentdetails`  
**Record Count:** ~2763 students  

**Key Columns:**
- `id` - Student system ID (Primary Key)
- `name` - Full student name  
- `reg_no` - Registration number
- `batch` - Batch/cohort identifier (e.g., "2023")
- `year` - Current academic year (1-4)
- `semester` - Semester (1-8)
- `section` - Section code (e.g., "A", "B", "CSE-1")
- `email` - Student email
- `department_id` - Department reference
- `is_active` - Active status flag

**VoxERP Usage:**
- `lookup_student(student_id=None, name=None)` - Find student by ID or name
- `resolve_student_id(name)` - Get ID from name
- `resolve_student_name(student_id)` - Get name from ID

**Example Query:**
```sql
SELECT id, name, reg_no, batch, year, semester, section, email, department_id
FROM user_accounts_studentdetails
WHERE LOWER(name) LIKE '%vijay%'
LIMIT 10;
```

**Important Notes:**
- Student names may contain special characters (e.g., "Vijayasri Vembu.T")
- Multiple students may have similar names (e.g., multiple Vijay-related names)
- `user_accounts_student` table is currently empty (do NOT use)

---

### 2. Courses

**Logical Entity:** Course / Subject  
**Real Table:** `course_management_course`  

**Key Columns:**
- `id` - Course ID (Primary Key)
- `course_code` - Course code (e.g., "CS101")
- `title` - Course title (e.g., "Data Structures")
- `year` - Academic year level (1-4)
- `semester` - Semester (1-8)
- `is_active` - Active status flag
- `department_id` - Department reference

**VoxERP Usage:**
- `lookup_course(course_code=None, title=None)` - Find course by code or title
- `get_enrollment(student_id)` - Get courses a student is enrolled in

**Example Query:**
```sql
SELECT id, course_code, title, year, semester, department_id
FROM course_management_course
WHERE course_code = 'CS101'
OR LOWER(title) LIKE '%data structures%';
```

---

### 3. Course Enrollment

**Logical Entity:** Enrollment  
**Real Table:** `course_management_courseenrollment`  

**Key Columns:**
- `id` - Enrollment record ID
- `student_id` - Student reference
- `course_id` - Course reference
- `batch` - Batch identifier
- `section` - Section code
- `enrollment_date` - Date of enrollment
- `academic_year` - Academic year
- `semester` - Semester
- `faculty_id` - Assigned faculty
- `department_id` - Department reference

**VoxERP Usage:**
- `get_enrollment(student_id)` - Get all courses a student is enrolled in

**Example Query:**
```sql
SELECT 
    ce.id, ce.course_id, ce.enrollment_date,
    c.course_code, c.title, c.year, c.semester
FROM course_management_courseenrollment ce
JOIN course_management_course c ON ce.course_id = c.id
WHERE ce.student_id = '12345';
```

---

### 4. Attendance

**Logical Entity:** Attendance  
**Real Tables:** 
- `student_management_daily_attendance` - Daily attendance records
- `student_management_hourattendance` - Hour-by-hour attendance (optional)

**Key Columns (daily_attendance):**
- `id` - Record ID (Primary Key)
- `student_id` - Student reference
- `course_id` - Course reference (nullable)
- `date` - Attendance date
- `full_day_status` - Full day attendance status (present/absent/unmarked)
- `morning_status` - Morning session status
- `afternoon_status` - Afternoon session status
- `marked_at` - Timestamp when attendance was marked
- `remarks` - Additional remarks
- `section` - Section code
- `semester` - Semester
- `year` - Academic year
- `faculty_id` - Faculty who marked attendance
- `academic_year` - Academic year

**VoxERP Usage:**
- `get_attendance(student_id, subject=None)` - Retrieve attendance records
- `mark_attendance(student_id, subject, date, status, actor_id)` - Record attendance

**Example Query:**
```sql
SELECT da.id, da.date, da.full_day_status, da.morning_status, da.afternoon_status,
       c.course_code, c.title
FROM student_management_daily_attendance da
LEFT JOIN course_management_course c ON da.course_id = c.id
WHERE da.student_id = '12345'
ORDER BY da.date DESC;
```

**Write Operation:**
```sql
INSERT INTO student_management_daily_attendance
(student_id, course_id, date, full_day_status, marked_at)
VALUES ('12345', 10, '2026-09-01', 'present', NOW());
```

---

### 5. Exam Records

**Logical Entity:** Exams  
**Real Table:** `examination_management_studentexam`  

**Key Columns:**
- `id` - Exam record ID (Primary Key)
- `student_id` - Student reference
- `reg_no` - Registration number (denormalized)
- `student_name` - Student name (denormalized)
- `course_code` - Course code
- `course_title` - Course title
- `department_code` - Department code
- `department_name` - Department name
- `batch` - Batch identifier
- `section` - Section code
- `exam_name` - Name of exam (e.g., "Midterm", "Final")
- `pattern_id` - Exam pattern reference
- `created_at` - Timestamp

**VoxERP Usage:**
- `get_marks(student_id, subject=None)` - Retrieve exam and marks information

**Example Query:**
```sql
SELECT se.id, se.exam_name, se.course_code, se.course_title, se.created_at
FROM examination_management_studentexam se
WHERE se.student_id = '12345'
ORDER BY se.created_at DESC;
```

---

### 6. Marks/Scores

**Logical Entity:** Marks  
**Real Table:** `examination_management_studentmark`  

**Key Columns:**
- `id` - Mark record ID
- `student_exam_id` - Reference to studentexam record
- `part_name` - Part/question identifier
- `question_number` - Question number
- `sub_question` - Sub-question identifier
- `option_letter` - Selected option (for MCQ)
- `max_marks` - Maximum marks for this question
- `marks_obtained` - Marks awarded
- `co_code_id` - Course outcome reference
- `level_code_id` - Difficulty level reference
- `created_at` - Timestamp

**VoxERP Usage:**
- `get_marks(student_id, subject=None)` - Aggregate marks by exam

**Example Query:**
```sql
SELECT 
    sm.part_name, sm.question_number, sm.marks_obtained, sm.max_marks
FROM examination_management_studentmark sm
WHERE sm.student_exam_id = '99999'
ORDER BY sm.question_number;
```

**Aggregation for VoxERP:**
```sql
SELECT 
    se.id, se.exam_name, se.course_code, se.course_title,
    SUM(sm.marks_obtained) as total_marks,
    SUM(sm.max_marks) as max_marks,
    (SUM(sm.marks_obtained) / SUM(sm.max_marks) * 100) as percentage
FROM examination_management_studentexam se
LEFT JOIN examination_management_studentmark sm ON se.id = sm.student_exam_id
WHERE se.student_id = '12345'
GROUP BY se.id;
```

---

### 7. Timetable

**Logical Entity:** Timetable / Schedule  
**Real Table:** `course_management_periodallocation`  

**Key Columns:**
- `id` - Record ID (Primary Key)
- `section` - Section code
- `year` - Academic year level (1-4)
- `semester` - Semester (1-8)
- `day` - Day of week (Monday, Tuesday, etc.)
- `first_period` - Course ID for period 1
- `second_period` - Course ID for period 2
- `third_period` - Course ID for period 3
- `fourth_period` - Course ID for period 4
- `fifth_period` - Course ID for period 5
- `sixth_period` - Course ID for period 6
- `seventh_period` - Course ID for period 7
- `eighth_period` - Course ID for period 8
- `nineth_period` - Course ID for period 9
- `tenth_period` - Course ID for period 10
- `department_id` - Department reference

**VoxERP Usage:**
- `get_timetable(student_id, year=None, semester=None)` - Get student's class schedule

**Example Query:**
```sql
SELECT 
    day, section, year, semester,
    first_period, second_period, third_period, fourth_period, fifth_period,
    sixth_period, seventh_period, eighth_period, nineth_period, tenth_period
FROM course_management_periodallocation
WHERE year = 3 AND semester = 5 AND section = 'CSE-A'
ORDER BY FIELD(day, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday');
```

---

## VoxERP-Specific Tables

### 8. Write Log (Audit Trail)

**Table:** `voxerp_write_log` (created by Person A)  

**Purpose:** Track all write operations (attendance marking, etc.) for audit and debugging.

**Columns:**
- `id` - Log entry ID
- `actor_id` - User who performed the action
- `action` - Action type (e.g., "mark_attendance")
- `target_student_id` - Student affected
- `course_id` - Course affected
- `attendance_date` - Date of attendance
- `status` - Status value (e.g., "present", "absent")
- `timestamp` - When the action occurred

**Example:**
```sql
INSERT INTO voxerp_write_log 
(actor_id, action, target_student_id, course_id, attendance_date, status)
VALUES ('teacher-1', 'mark_attendance', '12345', 10, '2026-09-01', 'present');
```

---

### 9. Demo Users (VoxERP Sprint Demo)

**Table:** `voxerp_demo_users` (created by Person C)  

**Purpose:** Demo user accounts for the sprint demonstration.

**Columns:**
- `id` - Demo user ID
- `role` - User role (student/teacher)
- `name` - Display name
- `real_student_id` - Optional reference to real student for testing

---

## Query Patterns

### Find a Student by Name (Fuzzy Match)
```sql
-- Exact match first
SELECT id, name, reg_no FROM user_accounts_studentdetails
WHERE LOWER(name) = LOWER('Vijayasri Vembu.T')
LIMIT 1;

-- Partial match if exact fails
SELECT id, name, reg_no FROM user_accounts_studentdetails
WHERE LOWER(name) LIKE LOWER('%Vijay%')
LIMIT 10;
```

### Get Student's Current Courses
```sql
SELECT 
    c.id, c.course_code, c.title, c.year, c.semester
FROM course_management_courseenrollment ce
JOIN course_management_course c ON ce.course_id = c.id
WHERE ce.student_id = '12345'
  AND c.year = 3
  AND c.semester = 5;
```

### Get Attendance Summary for a Student
```sql
SELECT 
    date, full_day_status, morning_status, afternoon_status
FROM student_management_daily_attendance
WHERE student_id = '12345'
  AND date BETWEEN '2026-08-01' AND '2026-08-31'
ORDER BY date;
```

### Get Marks with Totals
```sql
SELECT 
    se.exam_name, se.course_code, se.course_title,
    SUM(sm.marks_obtained) as obtained,
    SUM(sm.max_marks) as total,
    ROUND((SUM(sm.marks_obtained) / SUM(sm.max_marks) * 100), 2) as percentage
FROM examination_management_studentexam se
LEFT JOIN examination_management_studentmark sm ON se.id = sm.student_exam_id
WHERE se.student_id = '12345'
GROUP BY se.id, se.exam_name, se.course_code, se.course_title
ORDER BY se.created_at DESC;
```

### Get Class Timetable
```sql
SELECT 
    day, 
    first_period, second_period, third_period, fourth_period, fifth_period,
    sixth_period, seventh_period, eighth_period, nineth_period, tenth_period
FROM course_management_periodallocation
WHERE section = 'CSE-A' AND year = 3 AND semester = 5
ORDER BY FIELD(day, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday');
```

---

## Important Implementation Notes

### Parameterized Queries
All queries in `db_adapter.py` use parameterized queries with `%s` placeholders to prevent SQL injection.

```python
# CORRECT - parameterized
cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))

# WRONG - string concatenation
cursor.execute(f"SELECT * FROM students WHERE id = {student_id}")
```

### Connection Management
- Uses connection pooling (max 5 connections)
- Connections auto-close in `finally` blocks
- All database operations use try/except for error handling

### Subject/Course Matching
The adapter normalizes course names for fuzzy matching:
- Converts to lowercase
- Removes spaces and special characters
- Example: "DBMS", "DB-MS", "db ms" all normalize to "dbms"

### Handling Ambiguous Names
When multiple students match a name search, the function returns:
```python
{
    "status": "ambiguous",
    "candidates": [list of matching students],
    "message": "Found N students..."
}
```

This allows Person B's intent engine to ask for clarification rather than guessing.

---

## Testing

Run integration tests against the real database:

```bash
# Requires .env file with DB_* variables
python -m pytest tests/test_db_adapter_mariadb.py -v

# Run specific test
python -m pytest tests/test_db_adapter_mariadb.py::DbAdapterStudentLookupTests::test_lookup_student_by_name_vijay -v
```

---

## Future Enhancements (Phase 2)

- [ ] Support for multiple exam patterns
- [ ] Lab attendance tracking
- [ ] Course prerequisites and dependencies
- [ ] GPA calculations
- [ ] Bulk attendance import/export
- [ ] Exam schedules and date-time tracking
- [ ] Faculty assignment and course allocation

