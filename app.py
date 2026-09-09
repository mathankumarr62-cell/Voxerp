import datetime
import os
import sys
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory

load_dotenv()
import db_adapter
from intelligence.intent_engine import IntentEngine
from intelligence.rbac import authorize_request, data_router
from intelligence.response_generator import generate_response
from rag.retriever import retrieve_policy

app = Flask(__name__, static_folder=".", static_url_path="")

db_adapter.initialize_database()
intent_engine = IntentEngine()

if not intent_engine.gemma_available and intent_engine.client is None:
    try:
        from tests.test_person_b import FakeGeminiClient
        intent_engine.client = FakeGeminiClient()
        print("[SERVER LOG] GEMINI_API_KEY not set in environment/.env. Initialized offline FakeGeminiClient fallback.", flush=True)
    except Exception as e:
        print("[SERVER LOG] Could not load FakeGeminiClient fallback:", e, flush=True)


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/users", methods=["GET"])
def list_users():
    try:
        users = db_adapter.list_demo_users()
        return jsonify({"users": users})
    except Exception as exc:
        print(f"/users error: {exc}", flush=True)
        return jsonify({"users": [], "error": "Unable to load demo users."}), 500


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
        print(f"\n[SERVER LOG] Received /query: user_id='{user_id}', role='{role}', text='{text}'", flush=True)

        schema_map = db_adapter.build_schema_map()
        
        print("[SERVER LOG] Invoking IntentEngine.parse()...", flush=True)
        intent = intent_engine.parse(text, role, schema_map)
        print(f"[SERVER LOG] IntentEngine parsed result: {intent}", flush=True)

        # A missing subject is a conversational clarification, not a database
        # operation. Ask for it before authorization.
        if (
            intent.get("action") == "write"
            and intent.get("table") == "attendance"
            and not (intent.get("filters") or {}).get("subject")
        ):
            print(
                "[SERVER LOG] Write request missing subject. Asking for subject before authorization.",
                flush=True,
            )
            return jsonify({"reply_text": "Which subject should I mark absent?"})

        print("[SERVER LOG] Invoking authorize_request()...", flush=True)
        auth_res = authorize_request(user_id=user_id, role=role, intent=intent, text=text)
        print(f"[SERVER LOG] authorize_request decision: {auth_res}", flush=True)

        data_source = data_router.route(intent, text)
        print(f"[SERVER LOG] DataRouter selected source: {data_source}", flush=True)

        if not auth_res.get("allowed"):
            print("[SERVER LOG] Authorization DENIED or UNSUPPORTED. db_adapter will NOT be called.", flush=True)
            return jsonify({"reply_text": generate_response(auth_res)})

        if data_source == "rag":
            policy_context = retrieve_policy(role, text)
            print("[SERVER LOG] RAG policy context retrieved. SQL/db_adapter will NOT be called.", flush=True)
            return jsonify({
                "reply_text": generate_response({"policy_context": policy_context})
            })

        target_student_id = auth_res["target_student_id"]
        action = intent.get("action")
        table = intent.get("table")
        filters = intent.get("filters") or {}

        if action == "write":
            if table != "attendance":
                return jsonify({"reply_text": "I can't help with that request."})

            subject = filters.get("subject")
            if not subject:
                print("[SERVER LOG] Write request missing subject. Asking for subject without writing.", flush=True)
                return jsonify({"reply_text": "Which subject should I mark absent?"})

            status = filters.get("status") or "absent"
            period = filters.get("period")

            if period is None:
                print(
                    "[SERVER LOG] Write request missing attendance period. "
                    "Asking for period without writing.",
                    flush=True,
                )
                return jsonify({
                    "reply_text": f"Which period should I mark {status} for {subject}?"
                })

            if not isinstance(period, int) or not 1 <= period <= 10:
                print(
                    f"[SERVER LOG] Invalid attendance period: {period}",
                    flush=True,
                )
                return jsonify({
                    "reply_text": "Please specify a valid attendance period from 1 to 10."
                })

            date = filters.get("date") or datetime.date.today().isoformat()
            student_name = filters.get("student_name")
            target_display = student_name if student_name and student_name.lower() != "you" else "you"

            pending = {
                "student_id": target_student_id,
                "subject": subject,
                "date": date,
                "status": status,
                "period": period,
                "actor_id": user_id,
                "role": role,
            }

            print(f"[SERVER LOG] Write request authorized. Preparing confirmation request (db_adapter.mark_attendance NOT called yet). Pending payload: {pending}", flush=True)

            confirm_text = (
                f"Mark {target_display} {status} in {subject}, period {period} for today. "
                "Say yes or no."
            )

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
                print(f"[SERVER LOG] Calling db_adapter.get_attendance('{target_student_id}', '{subject}')", flush=True)
                result = db_adapter.get_attendance(target_student_id, subject)

            elif table == "marks":
                subject = filters.get("subject")
                print(f"[SERVER LOG] Calling db_adapter.get_marks('{target_student_id}', '{subject}')", flush=True)
                result = db_adapter.get_marks(target_student_id, subject)

            elif table == "timetable":
                print(f"[SERVER LOG] Calling db_adapter.get_timetable('{target_student_id}')", flush=True)
                result = db_adapter.get_timetable(target_student_id)

            else:
                print("[SERVER LOG] Unknown table for read intent.", flush=True)
                return jsonify({"reply_text": "I couldn't process that request."})

            print(f"[SERVER LOG] db_adapter result: {result}", flush=True)
            return jsonify({"reply_text": generate_response(result)})

        return jsonify({"reply_text": "I couldn't process that request."})

    except Exception as e:
        print("[SERVER LOG] ERROR in /query:", e, flush=True)
        return jsonify({"reply_text": "Something went wrong on my end, please try again."}), 500


@app.route("/confirm", methods=["POST"])
def confirm():
    data = request.get_json(silent=True) or {}
    decision = (data.get("confirm") or "").strip().lower()
    pending = data.get("pending") or {}

    print(f"\n[SERVER LOG] Received /confirm: decision='{decision}', pending={pending}", flush=True)

    required = [
        "student_id",
        "subject",
        "date",
        "status",
        "period",
        "actor_id",
        "role",
    ]

    if not all(k in pending for k in required):
        return jsonify({"reply_text": "I lost track of that request, please try again."}), 400

    if decision != "yes":
        print("[SERVER LOG] Confirmation decision is not 'yes'. db_adapter.mark_attendance will NOT be called.", flush=True)
        return jsonify({"reply_text": "Okay, no changes made."})

    try:
        role = pending.get("role")
        if not isinstance(role, str) or not role.strip():
            return jsonify({"reply_text": "I couldn't verify the current user role."}), 403

        period = pending.get("period")
        if not isinstance(period, int) or not 1 <= period <= 10:
            return jsonify({
                "reply_text": "I couldn't verify the attendance period. Please start the request again with a period from 1 to 10."
            }), 400
        confirm_intent = {
            "action": "write",
            "table": "attendance",
            "filters": {
                "student_id": pending["student_id"],
                "subject": pending["subject"],
                "date": pending["date"],
                "status": pending["status"],
                "period": period,
            },
        }

        auth_res = authorize_request(
            pending["actor_id"],
            role,
            confirm_intent,
            f"mark {pending['student_id']} {pending['status']} in {pending['subject']}",
        )

        if not auth_res.get("allowed"):
            print(
                f"[SERVER LOG] Confirmation re-authorization denied: {auth_res}",
                flush=True,
            )
            return jsonify({
                "reply_text": auth_res.get(
                    "message",
                    "You are not authorized to make that change.",
                )
            }), 403

        print(
            f"[SERVER LOG] Confirmation explicitly authorized. "
            f"Calling db_adapter.mark_attendance({pending})",
            flush=True,
        )

        result = db_adapter.mark_attendance(
            pending["student_id"],
            pending["subject"],
            pending["date"],
            pending["status"],
            actor_id=pending["actor_id"],
            period=period,
        )
        print(f"[SERVER LOG] db_adapter.mark_attendance result: {result}", flush=True)
        return jsonify({"reply_text": generate_response(result)})
    except Exception as e:
        print("[SERVER LOG] ERROR in /confirm:", e, flush=True)
        return jsonify({"reply_text": "Something went wrong while saving that, please try again."}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5050)