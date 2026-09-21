"""Create a nonprivileged local Django account using a verified ERP numeric ID."""
import argparse
import getpass
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--student-id', required=True)
    args = parser.parse_args()
    if not args.student_id.isascii() or not args.student_id.isdecimal():
        parser.error('Use the approved numeric ERP student ID, not a registration number or name.')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    import db_adapter
    if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3':
        parser.error('This command is restricted to the local Django application database.')
    if not db_adapter._real_db_enabled() or db_adapter._real_writes_enabled():
        parser.error('Select the authorized real ERP read-only environment first.')
    result = db_adapter.lookup_student(student_id=args.student_id)
    if result.get('status') != 'ok' or str(result['student']['id']) != args.student_id:
        parser.error('That exact ERP student ID could not be verified.')
    User = get_user_model()
    if User.objects.filter(username=args.student_id).exists():
        print('Account already exists; password and permissions left unchanged.')
        return
    password = getpass.getpass('Local demo password: ')
    if len(password) < 12 or password != getpass.getpass('Repeat password: '):
        parser.error('Passwords must match and contain at least 12 characters.')
    User.objects.create_user(username=args.student_id, password=password,
                             is_staff=False, is_superuser=False)
    print('Local student account created; credentials are not stored in source files.')


if __name__ == '__main__':
    main()
