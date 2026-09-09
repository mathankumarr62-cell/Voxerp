# VoxERP real ERP schema mapping

This mapping is based on a read-only metadata and relationship audit of the `ramco_academic_system` MariaDB database on 2026-09-06. It records observed schema and joins; it does not treat column names as declared relationships. The audited database has no declared foreign keys on the tables below.

The historical audit notes below are preserved. The consolidated-marks mapping is reconciled with the current adapter source; no new live database audit was performed during this documentation update.

## Tables and relationships

| Logical entity | Verified table | Primary key | Relationship used by VoxERP |
| --- | --- | --- | --- |
| Student | `user_accounts_studentdetails` | `id` | Authoritative student record for adapter lookups. `reg_no` is unique and links exam rows. |
| Course | `course_management_course` | `id` | `course_code`, `title`, `year`, `semester`, `department_id` identify course metadata. |
| Enrollment | `course_management_courseenrollment` | `id` | Observed joins: `student_id` -> student `id`; `course_id` -> course `id`. |
| Daily attendance | `student_management_daily_attendance` | `id` | Observed join: `student_id` -> student `id`. This table has no course field. |
| Hour attendance | `student_management_hourattendance` | `id` | Observed joins: `student_id` -> student `id`; `course_id` -> course `id`. Some rows do not match a course and are excluded by the adapter's inner join. |
| Consolidated marks | `examination_management_overallconsolidaterecord` | `id` (used by adapter) | Current `get_marks` filters `student_id` and joins `course_id` to course `id`; live validation remains pending. |
| Raw internal marks | `examination_management_studentinternalmark` | Not revalidated | Discoverable through `build_schema_map`; not the student-facing marks source and not summed by `get_marks`. |
| Student exam | `examination_management_studentexam` | `id` | Observed join: `reg_no` -> student `reg_no`; there is no `student_id` column. |
| Student mark | `examination_management_studentmark` | `id` | Observed join: `student_exam_id` -> student-exam `id`. |
| Class timetable | `course_management_periodallocation` | `id` | Student `year`, `semester`, and `section` select a class allocation. The period cells contain course **codes** (`varchar`), not course IDs. |
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
| Timetable | Student `year`, `semester`, `section` -> `course_management_periodallocation` with all three fields as parameters | `get_timetable`. Period values are course codes; lab schedule integration is unsupported. |
| Attendance write | `student_management_hourattendance`; target tuple is `student_id`, resolved course `id`, `date`, `period` | Code path exists but is disabled by default with `VOXERP_ALLOW_REAL_WRITES=False`. It may be enabled only for an explicitly authorized isolated database; no production/unknown-database write is supported. |

MariaDB query values are bound with connector placeholders. With `VOXERP_ALLOW_REAL_WRITES=False` or unset, real initialization and mutations are disabled. The gated initializer does contain CREATE/seed statements for `voxerp_write_log` and `voxerp_demo_users`; real mode alone is not the write-safety boundary. Keep the write flag disabled.

Consolidated assessment rows with missing positional values or nonnumeric marks are skipped; if no valid assessments remain, the adapter returns `no_data`. Historical student-exam/student-mark relationships above are not the current marks READ path.

Timetable selection currently filters year, semester and section, but not department. Period codes are resolved with a course lookup; unresolved codes remain in the response with null course ID/title. Department collisions and course-code uniqueness need live validation.

The MariaDB attendance UPDATE references `updated_at`, absent from the historical hourly column list. The attendance path also does not populate `voxerp_write_log`. Its gated implementation is not evidence of a validated production write workflow.

## Audit evidence and limits

Read-only checks confirmed populated tables and successful data joins for enrollment/student, enrollment/course, hourly-attendance/student, hourly-attendance/course, daily-attendance/student, exam/student by registration number, and mark/student-exam. The hourly attendance to course join is not total; unmatched rows remain untouched. Timetable values sampled from non-empty cells were course-code-shaped values and the column type is `varchar(200)`.

The database identity is not established as an isolated local clone. Therefore no write validation was performed and real-mode write tests must not be run until an owner explicitly identifies and authorizes an isolated database.

The final-result table `examination_management_result` was reported empty in the
team handoff. It is not queried by this adapter; no final semester results are
fabricated. Release checks cover populated consolidated marks, hourly attendance
and timetable for the explicitly selected validation student, not all ERP records.
