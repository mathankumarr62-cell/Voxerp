import os
import re
import datetime
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import db_adapter

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")

db_adapter.initialize_database()


def find_target_student(text_lower):
    """
    Find a student mentioned in text by name.
    This searches the real database for matching student names.
    Returns the first match or None.
    """
    # Extract potential student names from text
    # Look for capitalized words that might be names
    words = text_lower.split()

    for word in words:
        if len(word) > 2:  # Skip short words
            result = db_adapter.lookup_student(name=word)
            if result["status"] == "ok" and result["student"]:
                return result["student"]
            # If ambiguous, return first candidate
            elif result["status"] == "ambiguous" and result.get("candidates"):
                return result["candidates"][0]

    return None


def parse_intent(text, role):
    text_lower = text.lower().strip()

    if not text_lower:
        return {"action": "unknown", "table": None, "filters": {}}

    subjects = ["dbms", "operating systems", "os", "computer networks", "cn"]
    found_subject = None
    for s in subjects:
        if s in text_lower:
            found_subject = "Operating Systems" if s == "os" else (
                "Computer Networks" if s == "cn" else s.upper() if s == "dbms" else s.title()
            )
            break

    if "mark" in text_lower and "absent" in text_lower:
        target = find_target_student(text_lower)
        return {
            "action": "write",
            "table": "attendance",
            "filters": {"subject": found_subject, "status": "absent", "target": target},
        }

    if "attendance" in text_lower:
        return {"action": "read", "table": "attendance", "filters": {"subject": found_subject}}
    if "marks" in text_lower or "score" in text_lower:
        return {"action": "read", "table": "marks", "filters": {"subject": found_subject}}
    if "timetable" in text_lower or "schedule" in text_lower:
        return {"action": "read", "table": "timetable", "filters": {}}

    return {"action": "unknown", "table": None, "filters": {}}


def apply_rbac_read(user_id, role, filters):
    filters = dict(filters or {})
    filters["student_id"] = user_id
    return filters


def apply_rbac_write(user_id, role, filters):
    filters = dict(filters or {})
    target = filters.get("target")
    if role == "teacher" and target:
        filters["student_id"] = target["id"]
        filters["target_name"] = target["name"]
    else:
        filters["student_id"] = user_id
        filters["target_name"] = "you"
    return filters


def generate_response(result):
    if not result:
        return "Something went wrong, please try again."
    return result.get("message", "I couldn't process that.")


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/users", methods=["GET"])
def list_users():
    """Get list of demo users for the frontend dropdown."""
    try:
        conn = db_adapter._connect()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, role, name FROM voxerp_demo_users")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        users = [{"id": r["id"], "role": r["role"], "name": r["name"]} for r in rows]
        return jsonify({"users": users})
    except Exception as e:
        print(f"Error fetching users: {e}")
        return jsonify({"error": "Failed to fetch users"}), 500


@app.route("/query", methods=["POST"])
def query():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    user_id = data.get("user_id")
    role = data.get("role")

    if not user_id or not role:
        return jsonify({"reply_text": "No demo user selected. Please pick a user first."}), 400

    if not text:
        return jsonify({"reply_text": "I didn't catch that, try again."})

    try:
        intent = parse_intent(text, role)

        if intent["action"] == "unknown":
            return jsonify({"reply_text": "I couldn't find that. Try asking about attendance, marks, or timetable."})

        if intent["action"] == "write":
            subject = intent["filters"].get("subject")
            if not subject:
                return jsonify({"reply_text": "Which subject should I mark absent?"})

            rbac_filters = apply_rbac_write(user_id, role, intent["filters"])
            target_name = rbac_filters["target_name"]
            today = datetime.date.today().isoformat()

            pending = {
                "student_id": rbac_filters["student_id"],
                "subject": subject,
                "date": today,
                "status": "absent",
                "actor_id": user_id,
            }

            confirm_text = "Mark " + target_name + " absent in " + subject + " for today. Say yes or no."
            return jsonify({
                "reply_text": confirm_text,
                "requires_confirmation": True,
                "pending": pending,
            })

        filters = apply_rbac_read(user_id, role, intent["filters"])

        if intent["table"] == "attendance":
            subject = filters.get("subject")
            if not subject:
                return jsonify({"reply_text": "Which subject would you like attendance for?"})
            result = db_adapter.get_attendance(filters["student_id"], subject)

        elif intent["table"] == "marks":
            subject = filters.get("subject")
            if not subject:
                return jsonify({"reply_text": "Which subject would you like marks for?"})
            result = db_adapter.get_marks(filters["student_id"], subject)

        elif intent["table"] == "timetable":
            result = db_adapter.get_timetable(filters["student_id"])

        else:
            return jsonify({"reply_text": "I couldn't process that request."})

        return jsonify({"reply_text": generate_response(result)})

    except Exception as e:
        print("ERROR in /query:", e)
        return jsonify({"reply_text": "Something went wrong on my end, please try again."}), 500


@app.route("/confirm", methods=["POST"])
def confirm():
    data = request.get_json(silent=True) or {}
    decision = (data.get("confirm") or "").strip().lower()
    pending = data.get("pending") or {}

    required = ["student_id", "subject", "date", "status", "actor_id"]
    if not all(k in pending for k in required):
        return jsonify({"reply_text": "I lost track of that request, please try again."}), 400

    if decision != "yes":
        return jsonify({"reply_text": "Okay, no changes made."})

    try:
        result = db_adapter.mark_attendance(
            pending["student_id"],
            pending["subject"],
            pending["date"],
            pending["status"],
            actor_id=pending["actor_id"],
        )
        return jsonify({"reply_text": generate_response(result)})
    except Exception as e:
        print("ERROR in /confirm:", e)
        return jsonify({"reply_text": "Something went wrong while saving that, please try again."}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5050)