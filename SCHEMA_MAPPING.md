# VoxERP real ERP schema mapping

This mapping is based on a read-only metadata and relationship audit of the `ramco_academic_system` MariaDB database on 2026-09-06. It records observed schema and joins; it does not treat column names as declared relationships. The audited database has no declared foreign keys on the tables below.

The historical audit notes below are preserved. The 2026-09-21 local-dump revalidation and corrections at the end supersede claims of pending validation, absent foreign keys, and timetable selection without department.

## Tables and relationships

| Logical entity | Verified table | Primary key | Relationship used by VoxERP |
| --- | --- | --- | --- |
| Student | `user_accounts_studentdetails` | `id` | Authoritative student record for adapter lookups. `reg_no` is unique and links exam rows. |
| Course | `course_management_course` | `id` | `course_code`, `title`, `year`, `semester`, `department_id` identify course metadata. |
| Enrollment | `course_management_courseenrollment` | `id` | Observed joins: `student_id` -> student `id`; `course_id` -> course `id`. |
| Daily attendance | `student_management_daily_attendance` | `id` | Observed join: `student_id` -> student `id`. This table has no course field. |
| Hour attendance | `student_management_hourattendance` | `id` | Observed joins: `student_id` -> student `id`; `course_id` -> course `id`. Some rows do not match a course and are excluded by the adapter's inner join. |
| Consolidated marks | `examination_management_overallconsolidaterecord` | `id` (used by adapter) | Current `get_marks` filters `student_id` and joins `course_id` to course `id`; local restored-dump validation passed (IAT1 62/100, IAT2 77/100 for approved student 917/course IT25201). |
| Raw internal marks | `examination_management_studentinternalmark` | Not revalidated | Discoverable through `build_schema_map`; not the student-facing marks source and not summed by `get_marks`. |
| Student exam | `examination_management_studentexam` | `id` | Observed join: `reg_no` -> student `reg_no`; there is no `student_id` column. |
| Student mark | `examination_management_studentmark` | `id` | Observed join: `student_exam_id` -> student-exam `id`. |
| Class timetable | `course_management_periodallocation` | `id` | Student `department_id`, `year`, `semester`, and `section` select a class allocation. The period cells contain course **codes** (`varchar`), not course IDs. |
| Lab timetable | `course_management_lab_timetable` | `id` | Present, but its `lab_id` relationship and use for a student schedule were not verified; unsupported. |

`auth_user`, `auth_group`, `auth_permission`, `user_accounts_globalusers`, and `user_accounts_student` exist. Their role and student relationships were not audited, so VoxERP does not map ERP roles from them. Application authentication and RBAC remain outside this adapter.

## Exact relevant columns

| Table | Columns used or relevant to the mapping |
| --- | --- |
| `user_accounts_studentdetails` | `id`, `name`, `reg_no`, `batch`, `year`, `semester`, `section`, `email`, `department_id`, `is_active`, `is_discontinued` |
| `course_management_course` | `id`, `course_code`, `title`, `year`, `semester`, `is_active`, `department_id`, `elective_id`, `regulation_id` |
| `course_management_courseenrollment` | `id`, `student_id`, `course_id`, `batch`, `section`, `enrollment_date`, `enroll`, `academic_year`, `semester`, `year`, `faculty_id`, `department_id`, `regulation_id`, `is_open_elective` |
| `student_management_daily_attendance` | `id`, `date`, `student_id`, `full_day_status`, `morning_status`, `afternoon_status`, `remarks`, `marked_at`, `faculty_id`, `marked_by_id`, `updated_by_id`, `academic_year`, `year`, `semester`, `section` |
| `student_management_hourattendance` | `id`, `student_id`, `course_id`, `date`, `period`, `status`, `remarks`, `marked_at`, `faculty_id`, `department_id`, `academic_year`, `year`, `semester`, `section`, `batch`, `course_plan_id` |
| `examination_management_overallconsolidaterecord` | Current code uses `id`, `student_id`, `course_id`, `created_at`, `theory_assessment`, `theory_max_mark`, `theory_actual_mark`, `activity_assessment`, `activity_max_mark`, `activity_actual_mark`, `practical_assessment`, `practical_max_mark`, `practical_actual_mark`; verify against the target database. |
| `examination_management_studentexam` | `id`, `reg_no`, `student_name`, `course_code`, `course_title`, `exam_name`, `created_at`, `batch`, `section`, `department_code`, `department_name`, `pattern_id` |
| `examination_management_studentmark` | `id`, `student_exam_id`, `part_name`, `question_number`, `sub_question`, `option_letter`, `max_marks`, `marks_obtained`, `created_at`, `co_code_id`, `level_code_id` |
| `course_management_periodallocation` | `id`, `section`, `year`, `semester`, `day`, `first_period` through `tenth_period` (including the schema spelling `nineth_period`), `department_id` |

## VoxERP operation mapping

| Operation | Table(s), join, and parameter | Result / support |
| --- | --- | --- |
| Student lookup | `user_accounts_studentdetails`; `id`, case-insensitive `reg_no`, or case-insensitive name | `lookup_student`; exact lookup precedes bounded partial-name results and reports ambiguity. |
| Course lookup | `course_management_course`; `course_code` or title | `lookup_course`. No enrollment is assumed from a course lookup. |
| Enrollment | `course_management_courseenrollment ce JOIN course_management_course c ON ce.course_id=c.id`; `ce.student_id=%s` | `get_enrollment`; only rows with a verified course join are returned. |
| Daily attendance | `student_management_daily_attendance`; `student_id=%s` | `get_attendance(student_id)` returns overall daily status; it cannot answer a subject question. |
| Subject attendance | `student_management_hourattendance ha JOIN course_management_course c ON ha.course_id=c.id`; `ha.student_id=%s`, then normalized code/title match | `get_attendance(student_id, subject)`. Orphaned course rows are not returned. |
| Student-facing marks | `examination_management_overallconsolidaterecord o INNER JOIN course_management_course c ON o.course_id=c.id`; `o.student_id=%s` | `get_marks` parses theory, activity and practical assessment names/max/actual values from comma-separated fields; optional normalized course code/title filter. No raw question-level SUM is used. |
| Timetable | Student `department_id`, `year`, `semester`, `section` -> `course_management_periodallocation` with all four fields as parameters | `get_timetable`. Period values are course codes; lab schedule integration is unsupported. |
| Attendance write | `student_management_hourattendance`; target tuple is `student_id`, resolved course `id`, `date`, `period` | Code path exists but is disabled by default with `VOXERP_ALLOW_REAL_WRITES=False`. It may be enabled only for an explicitly authorized isolated database; no production/unknown-database write is supported. |

MariaDB query values are bound with connector placeholders. With `VOXERP_ALLOW_REAL_WRITES=False` or unset, real initialization and mutations are disabled. The gated initializer does contain CREATE/seed statements for `voxerp_write_log` and `voxerp_demo_users`; real mode alone is not the write-safety boundary. Keep the write flag disabled.

Consolidated assessment rows with missing positional values or nonnumeric marks are skipped; if no valid assessments remain, the adapter returns `no_data`. Historical student-exam/student-mark relationships above are not the current marks READ path.

Timetable selection now filters department, year, semester and section. Course-code resolution is restricted to the same department; unresolved codes remain in the response with null course ID/title. The 2026-09-21 audit below proves why the department predicate is required.

The MariaDB attendance UPDATE references `updated_at`, absent from the historical hourly column list. The attendance path also does not populate `voxerp_write_log`. Its gated implementation is not evidence of a validated production write workflow.

## Audit evidence and limits

Read-only checks confirmed populated tables and successful data joins for enrollment/student, enrollment/course, hourly-attendance/student, hourly-attendance/course, daily-attendance/student, exam/student by registration number, and mark/student-exam. The hourly attendance to course join is not total; unmatched rows remain untouched. Timetable values sampled from non-empty cells were course-code-shaped values and the column type is `varchar(200)`.

The database identity is not established as an isolated local clone. Therefore no write validation was performed and real-mode write tests must not be run until an owner explicitly identifies and authorizes an isolated database.

The final-result table `examination_management_result` was reported empty in the
team handoff. It is not queried by this adapter; no final semester results are
fabricated. Release checks cover populated consolidated marks, hourly attendance
and timetable for the explicitly selected validation student, not all ERP records.


## 2026-09-21 authorized local dump audit

The authorized dump was restored unchanged into an isolated MariaDB 12.3.3 instance on 127.0.0.1:3307. All 298 tables were imported; historical orphan rows required session-only disabled foreign-key checks during import. Normal connections retain checks. The application account has SELECT only; server read-only mode is ON and `VOXERP_ALLOW_REAL_WRITES=False`.

Counts: 2,763 students; 965 courses; 35,742 enrollments; 248,032 daily attendance rows; 1,392,751 hourly rows; 3,380 consolidated marks rows; 265 class allocations; 1 lab timetable row. Unlike the earlier metadata snapshot, this dump contains declared foreign-key statements. Their existence does not define VoxERP authorization semantics.

### Proven timetable defect and narrow adapter correction

Student 917 is department 2/year 2/semester 3/section A. The old query selected 15 allocation rows from departments 1, 7 and 9 (five each). There are zero matching department-2 allocations for this class; department 2's available second-year timetable is semester 4. Returning the old rows disclosed unrelated department schedules. The adapter now binds department in allocation and course-code lookup queries. Regression tests assert the predicate and fail-closed missing-department behavior. No other finalized adapter logic was rewritten.

Student 917 correctly receives `no_data`. Student 44 has a department-1/year-3/semester-5/section-A schedule; this provides a real, separately authenticated timetable demonstration. Updating student/class semester values or creating a schedule would require authoritative ERP data maintenance and is not performed.

### Teacher: candidate relationship exists, authorization is not yet defined

`course_management_courseenrollment.faculty_id` joins `faculty_management_general_information.id` for 35,641 of 35,742 enrollment rows; 101 have NULL faculty. There are 175 distinct non-NULL faculty references. Joining the same field to the faculty table's `faculty_id` employee identifier yields zero matches. Therefore the IDs must not be interchanged.

Candidate teaching scope includes enrollment `student_id`, `course_id`, `faculty_id`, `department_id`, `academic_year`, `year`, `semester`, `section`, `enroll`, and `is_open_elective`. Faculty records contain a separate employee identifier. Student details also contain `ca_id` and `mentor_id` references. These are different relationships and cannot be treated as one unrestricted teacher/class permission.

Required owner decisions before enabling teacher academic access:

- A protected mapping from an authenticated Django teacher account to the faculty primary key; the student-username contract does not define this.
- Whether teacher access is based on active course enrollment, class-adviser assignment, mentorship, or another approved relationship.
- Current term/date validity, enrollment status, elective/cross-department handling, and the permitted operations/fields per course and student.
- Read versus attendance-write authority and revocation behavior. A matching class label is insufficient to authorize every course's marks or attendance.

Teacher access remains fail-closed. The earlier statement that the schema contains no relationship at all is superseded: relationships exist, but the end-to-end identity and permission contract is unverified.

### HOD/Admin: permission rows are not an approved VoxERP role contract

The schema contains `user_accounts_globalusers` with string `role_id`/`employee_id`, `faculty_management_faculty_data_permission` with all-faculty/department-faculty flags, and `student_management_studentmanagementpermissions` with function/permission/role fields. Faculty-data permissions do not automatically authorize student marks, attendance or timetable. The historical sprint specifies student self-access and scoped teachers, not an HOD/Admin academic operation matrix.

Required: authoritative role assignment, account-to-employee mapping, department boundary (including shared/elective courses), exact academic read/write permissions, term validity and revocation rules. Until supplied, Admin/HOD groups and Django superusers are mapped to undefined roles and denied by RBAC; they never fall through to student permissions.
