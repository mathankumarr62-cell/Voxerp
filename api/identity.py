"""Trusted Django identity boundary; no request fields or model output are used."""
from dataclasses import dataclass
import os
import re
import db_adapter

@dataclass(frozen=True)
class Identity:
    user_id: str
    role: str

class AuthenticatedIdentityResolver:
    """Institutional integration point for a protected account binding.

    Numeric usernames are a provisioned local-demo convention, not proof
    that an arbitrary institutional account owns an ERP student record.
    """
    def resolve(self, user):
        if not user.is_authenticated or not user.is_active:
            return Identity("", "unverified")
        groups = {name.strip().lower() for name in user.groups.values_list("name", flat=True)}
        if user.is_superuser or "admin" in groups:
            role = "admin"
        elif "hod" in groups:
            role = "hod"
        elif user.is_staff or groups.intersection({"teacher", "faculty"}):
            role = "teacher"
        else:
            role = "student"
        if db_adapter._real_db_enabled() and (
            os.getenv("VOXERP_IDENTITY_MODE") != "local_demo"
            or os.getenv("VOXERP_ENV", "development").lower() == "production"
            or (role == "student" and not re.fullmatch(r"[1-9][0-9]*", user.username))
        ):
            return Identity("", "unverified")
        return Identity(user.username, role)

def current_student_is_active(student_id):
    """Refresh revocation evidence after RBAC and before private records."""
    if not db_adapter._real_db_enabled():
        return True
    if not isinstance(student_id, str) or not re.fullmatch(r"[1-9][0-9]*", student_id):
        return False
    conn = cursor = None
    try:
        conn = db_adapter._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT is_active, is_discontinued FROM user_accounts_studentdetails WHERE id = %s",
            (student_id,),
        )
        rows = cursor.fetchall()
        return len(rows) == 1 and rows[0] == (1, 0)
    except Exception:
        return False
    finally:
        db_adapter._close_cursor(cursor)
        db_adapter._close_connection(conn)
