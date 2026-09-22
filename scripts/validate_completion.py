"""Read-only local ERP + actual Gemma/Django validation. No academic data is printed."""
import os
from pathlib import Path
import secrets
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from scripts.local_demo import environment
    os.environ.update(environment())
    with tempfile.TemporaryDirectory(prefix='voxerp-validation-') as temporary:
        os.environ['VOXERP_APP_DB'] = str(Path(temporary) / 'auth.sqlite3')
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
        import django
        django.setup()
        from django.core.management import call_command
        from django.contrib.auth import get_user_model
        from django.test import Client
        import db_adapter
        from intelligence.response_generator import generate_response
        from api import views
        assert views.service.engine.gemma_available, 'Actual local Gemma unavailable'
        print('PASS: actual pinned local Gemma loaded')
        call_command('migrate', verbosity=0)
        conn = db_adapter._get_connection()
        cursor = conn.cursor()
        def rows(sql, params=()):
            cursor.execute(sql, params)
            return cursor.fetchall()
        assert rows('SELECT @@port, @@read_only')[0] == (3307, 'ON')
        grants = rows('SHOW GRANTS')
        assert any('GRANT SELECT ON' in row[0] for row in grants)
        assert not any('ALL PRIVILEGES' in row[0] for row in grants)
        print('PASS: loopback clone, server read-only, SELECT account, writes disabled')
        students = [str(row[0]) for row in rows('''SELECT DISTINCT s.id
            FROM user_accounts_studentdetails s
            JOIN examination_management_overallconsolidaterecord o ON o.student_id=s.id
            WHERE s.is_active=1 AND s.is_discontinued=0 ORDER BY s.id LIMIT 2''')]
        students = list(dict.fromkeys(students + ['44', '917']))
        password = secrets.token_urlsafe(32)
        responses = []
        for student in students:
            get_user_model().objects.create_user(username=student, password=password)
            client = Client(enforce_csrf_checks=True)
            login = client.get('/login/')
            # Use the actual password login endpoint and CSRF/session middleware.
            token = client.cookies['csrftoken'].value
            response = client.post('/login/', {'username':student, 'password':password,
                                               'csrfmiddlewaretoken':token})
            assert response.status_code == 302
            csrf = client.cookies['csrftoken'].value
            def query(text):
                response = client.post('/api/query/', {'text':text, 'student_id':'forged', 'role':'admin'},
                    content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
                assert response.status_code == 200, (text, response.status_code)
                return response.json()['reply_text']
            marks = db_adapter.get_marks(student)
            raw = rows('''SELECT o.id,o.theory_assessment,o.theory_max_mark,o.theory_actual_mark,
                o.activity_assessment,o.activity_max_mark,o.activity_actual_mark,
                o.practical_assessment,o.practical_max_mark,o.practical_actual_mark
                FROM examination_management_overallconsolidaterecord o
                INNER JOIN course_management_course c ON c.id=o.course_id WHERE o.student_id=%s''', (student,))
            for result in marks.get('rows', []):
                record = next(row for row in raw if row[0] == result['exam_id'])
                triples = []
                for start in (1,4,7):
                    fields = [str(value or '').split(',') for value in record[start:start+3]]
                    triples += list(zip(*fields))
                assert any(name.strip()==result['exam_name'] and float(maximum)==result['max_marks']
                           and float(actual)==result['marks_obtained'] for name,maximum,actual in triples
                           if maximum.strip() and actual.strip())
            actual = query('Show my marks')
            assert actual == generate_response(marks), 'marks inference/result mismatch'
            responses.append(actual)
            for subject in [None] + ([marks['rows'][0]['course_code'], marks['rows'][0]['course_title']] if marks.get('rows') else []):
                expected = db_adapter.get_attendance(student, subject)
                if subject:
                    text = f'What is my attendance in {subject}?'
                else:
                    text = 'Show my attendance'
                assert " ".join(query(text).split()) == " ".join(generate_response(expected).split()), 'attendance inference/result mismatch'
            hourly = db_adapter.get_attendance(student, hourly=True)
            raw_ids = {row[0] for row in rows('''SELECT ha.id FROM student_management_hourattendance ha
                INNER JOIN course_management_course c ON c.id=ha.course_id WHERE ha.student_id=%s''', (student,))}
            if hourly['status'] != 'ambiguous':
                assert {row['id'] for row in hourly.get('rows', [])} == raw_ids
            actual = query('How many periods was I absent?')
            assert actual == generate_response(hourly), 'hourly inference/result mismatch'
            expected = db_adapter.get_timetable(student)
            allocation_count = rows('''SELECT COUNT(*) FROM course_management_periodallocation p
                JOIN user_accounts_studentdetails s ON p.department_id=s.department_id AND p.year=s.year
                AND p.semester=s.semester AND p.section=s.section WHERE s.id=%s''', (student,))[0][0]
            assert bool(expected.get('rows')) == bool(allocation_count)
            assert query('Show my timetable') == generate_response(expected)
            assert query('Show my UNKNOWNCOURSE999 marks') == generate_response(db_adapter.get_marks(student, 'UNKNOWNCOURSE999'))
            other = next(value for value in students if value != student)
            assert 'only access your own' in query(f'Show student {other} marks')
            assert client.post('/api/query/', {'text':'Show my marks'}, content_type='application/json').status_code == 403
            print('PASS: authenticated student', student, 'SQL agreement, course names/codes, daily/hourly attendance, timetable, no data, cross-student denial, CSRF')
        assert len(set(responses)) > 1, 'Selected students must demonstrate differing data'
        print('PASS: changing authenticated student changes SQL-backed response')
        cursor.close(); conn.close()
        print('PASS: no ERP writes; temporary authentication database only')

if __name__ == '__main__':
    main()
