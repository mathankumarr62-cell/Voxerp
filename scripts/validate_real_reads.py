"""Explicit live READ-only validation; never collected by pytest. No credentials/results logged."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--student-id", required=True)
    parser.add_argument("--subject", required=True)
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not os.getenv("DB_USER") or not os.getenv("DB_PASSWORD"):
        print("SKIP: configured database credentials are unavailable")
        return 2
    os.environ.update(VOXERP_USE_REAL_DB="True", VOXERP_ALLOW_REAL_WRITES="False",
                      VOXERP_INITIALIZE_DATABASE="False", VOXERP_ENV="production",
                      VOXERP_OFFLINE_MODE="False", VOXERP_AUTH_MODE="proxy",
                      VOXERP_TRUSTED_PROXY_CIDRS="127.0.0.1/32",
                      VOXERP_ROLE_GROUPS="read-validation-students:student",
                      VOXERP_PENDING_SECRET=secrets.token_urlsafe(32))
    try:
        with socket.create_connection((os.getenv("DB_HOST", "localhost"), int(os.getenv("DB_PORT", "3306"))), timeout=5):
            pass
        print("PASS: TCP database port")
    except OSError:
        print("FAIL: TCP connectivity (no authentication attempted)")
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
        category = {1045: "account/host or authentication denied (DBA must distinguish)",
                    1130: "host authorization denied", 1044: "database permission denied",
                    1049: "database not found"}.get(exc.errno, "database connection/configuration")
        print("FAIL:", category)
        return 1
    db_adapter._get_connection = readonly_connection
    print("PASS: MariaDB authentication and database selection; sessions forced read-only")
    results = {
        "marks": db_adapter.get_marks(args.student_id, args.subject),
        "attendance": db_adapter.get_attendance(args.student_id, args.subject),
        "timetable": db_adapter.get_timetable(args.student_id),
    }
    passed = True
    for name, result in results.items():
        ok = result.get("status") == "ok" and bool(result.get("rows"))
        print(("PASS:" if ok else "FAIL:"), name, "READ", result.get("status"))
        passed = passed and ok
    if args.student_id == "917" and args.subject == "IT25201":
        rows = results["marks"].get("rows", [])
        for label, score in [("IAT1", 62), ("IAT2", 77)]:
            ok = any(str(r["exam_name"]).replace(" ", "").upper() == label and r["marks_obtained"] == score and r["max_marks"] == 100 for r in rows)
            print(("PASS:" if ok else "FAIL:"), "historical marks expectation", label)
            passed = passed and ok
    import app
    from intelligence.intent_engine import IntentEngine
    class Models:
        def generate_content(self, **kwargs):
            return type("Response", (), {"text": json.dumps(intent)})()
    app.intent_engine = IntentEngine(client=type("Client", (), {"models": Models()})())
    headers = {"X-Forwarded-User": "read-validation-principal",
               "X-Forwarded-Student-Id": args.student_id,
               "X-Forwarded-Groups": "read-validation-students"}
    client = app.app.test_client()
    for table in results:
        intent = {"action": "read", "table": table, "filters": {"subject": args.subject if table != "timetable" else None}}
        response = client.post("/query", headers=headers, json={"text": "Show my " + table})
        ok = response.status_code == 200 and response.json["reply_text"] == app.generate_response(results[table])
        print(("PASS:" if ok else "FAIL:"), "Flask/RBAC/adapter", table, "(inference stubbed)")
        passed = passed and ok
    intent = {"action": "read", "table": "marks", "filters": {"student_id": "other-student"}}
    response = client.post("/query", headers=headers, json={"text": "Show another student's marks"})
    ok = response.status_code == 403
    print(("PASS:" if ok else "FAIL:"), "cross-student rejection")
    print("Real ERP writes: disabled; no write operation invoked")
    return 0 if passed and ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("FAIL: validation could not complete (details suppressed to protect credentials)")
        raise SystemExit(1)
