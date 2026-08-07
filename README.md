# VoxERP — Person A Deliverable

This package implements the Person A data-layer foundation for the VoxERP sprint demo.

## Included pieces

- SQLite-backed mock database with seed data for students, subjects, attendance, marks, timetable, demo users, and a write log
- Adapter functions for reading and writing attendance data
- Normalization for subject names so inputs like "DBMS", "dbms", and "DB MS" resolve consistently
- Explicit result shapes for the two important edge cases:
  - "not_found" for unknown students or subjects
  - "no_data" when the student exists but no records are present
- A schema map generator that exposes the available tables and columns to the rest of the team

## Adapter API

- `get_attendance(student_id, subject)`
- `get_marks(student_id, subject)`
- `get_timetable(student_id)`
- `mark_attendance(student_id, subject, date, status)`

## Quick start

```bash
python db_adapter.py
```

The module initializes the SQLite database, seeds the demo data, and prints a short sample of the generated schema map.
