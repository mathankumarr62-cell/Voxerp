"""Explicit live READ-only validation; never collected by pytest. No credentials/results logged."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--student-id", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--timetable-student-id", help="Separately approved student with a populated exact class timetable")
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not os.getenv("DB_USER") or not os.getenv("DB_PASSWORD"):
        print("ENVIRONMENT CONFIGURATION FAILURE: database credentials unavailable")
        return 2
    os.environ.update(VOXERP_USE_REAL_DB="True", VOXERP_ALLOW_REAL_WRITES="False",
                      VOXERP_INITIALIZE_DATABASE="False", VOXERP_ENV="production",
                      VOXERP_OFFLINE_MODE="False")
    try:
        with socket.create_connection((os.getenv("DB_HOST", "localhost"), int(os.getenv("DB_PORT", "3306"))), timeout=5):
            pass
        print("PASS: TCP database port")
    except OSError:
        print("DATABASE AVAILABILITY / NETWORK FAILURE: TCP unavailable; firewall/Tailscale cause unverified")
        return 1
    import mariadb
    import db_adapter
    def readonly_connection():
        conn = mariadb.connect(**db_adapter.DB_CONFIG, connect_timeout=5)
        try:
            cursor = conn.cursor()
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.close()
            return conn
        except Exception:
            conn.close()
            raise
    try:
        conn = readonly_connection()
        conn.close()
    except mariadb.Error as exc:
        category = {1045: "DATABASE AUTHENTICATION FAILURE: account/host or credentials denied",
                    1130: "host authorization denied", 1044: "database permission denied",
                    1049: "database not found"}.get(exc.errno, "database connection/configuration")
        print("FAIL:", category)
        return 1
    db_adapter._get_connection = readonly_connection
    print("PASS: MariaDB authentication and database selection; sessions forced read-only")
    results = {
        "marks": db_adapter.get_marks(args.student_id, args.subject),
        "attendance": db_adapter.get_attendance(args.student_id, args.subject),
        "timetable": db_adapter.get_timetable(args.timetable_student_id or args.student_id),
    }
    passed = True
    for name, result in results.items():
        ok = result.get("status") == "ok" and bool(result.get("rows"))
        print(("PASS:" if ok else "FAIL:"), name, "READ", result.get("status"))
        passed = passed and ok
    from api.services import Identity, VoxERPService
    from intelligence.response_generator import generate_response
    class Engine:
        def parse(self, *args):
            return intent
    service = VoxERPService(Engine())
    for table in results:
        intent = {"action": "read", "table": table, "filters": {"subject": args.subject if table != "timetable" else None}}
        identity_id = (args.timetable_student_id or args.student_id) if table == "timetable" else args.student_id
        response = service.query(Identity(identity_id, "student"), "Show my " + table)
        ok = response["status"] == 200 and response["reply_text"] == generate_response(results[table])
        print(("PASS:" if ok else "FAIL:"), "Django service/RBAC/adapter", table, "(inference stubbed)")
        passed = passed and ok
    intent = {"action": "read", "table": "marks", "filters": {"student_id": "other-student"}}
    response = service.query(Identity(args.student_id, "student"), "Show another student's marks")
    ok = "only access your own" in response["reply_text"]
    print(("PASS:" if ok else "FAIL:"), "cross-student rejection")
    print("Real ERP writes: disabled; no write operation invoked")
    return 0 if passed and ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("FAIL: validation could not complete (details suppressed to protect credentials)")
        raise SystemExit(1)
