import datetime
from flask import Flask, request, jsonify, send_from_directory
import db_adapter
from intelligence.intent_engine import IntentEngine
from intelligence.rbac import authorize_request
from intelligence.response_generator import generate_response

app = Flask(__name__, static_folder=".", static_url_path="")

db_adapter.initialize_database()
intent_engine = IntentEngine()


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/users", methods=["GET"])
def list_users():
    conn = db_adapter._connect()
    try:
        rows = conn.execute("SELECT id, role, name FROM demo_users").fetchall()
        users = [{"id": r["id"], "role": r["role"], "name": r["name"]} for r in rows]
        return jsonify({"users": users})
    finally:
        conn.close()


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
        schema_map = db_adapter.build_schema_map()
        intent = intent_engine.parse(text, role, schema_map)

        auth_res = authorize_request(user_id=user_id, role=role, intent=intent, text=text)
        if not auth_res.get("allowed"):
            return jsonify({"reply_text": generate_response(auth_res)})

        target_student_id = auth_res["target_student_id"]
        action = intent.get("action")
        table = intent.get("table")
        filters = intent.get("filters") or {}

        if action == "write":
            if table != "attendance":
                return jsonify({"reply_text": "I can't help with that request."})

            subject = filters.get("subject")
            if not subject:
                return jsonify({"reply_text": "Which subject should I mark absent?"})

            status = filters.get("status") or "absent"
            date = filters.get("date") or datetime.date.today().isoformat()
            student_name = filters.get("student_name")
            target_display = student_name if student_name and student_name.lower() != "you" else "you"

            pending = {
                "student_id": target_student_id,
                "subject": subject,
                "date": date,
                "status": status,
                "actor_id": user_id,
            }

            confirm_text = f"Mark {target_display} {status} in {subject} for today. Say yes or no."
            return jsonify({
                "reply_text": confirm_text,
                "requires_confirmation": True,
                "pending": pending,
            })

        if action == "read":
            if table == "attendance":
                subject = filters.get("subject")
                if not subject:
                    return jsonify({"reply_text": "Which subject would you like attendance for?"})
                result = db_adapter.get_attendance(target_student_id, subject)

            elif table == "marks":
                subject = filters.get("subject")
                if not subject:
                    return jsonify({"reply_text": "Which subject would you like marks for?"})
                result = db_adapter.get_marks(target_student_id, subject)

            elif table == "timetable":
                result = db_adapter.get_timetable(target_student_id)

            else:
                return jsonify({"reply_text": "I couldn't process that request."})

            return jsonify({"reply_text": generate_response(result)})

        return jsonify({"reply_text": "I couldn't process that request."})

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