import os
import secrets
import threading
import datetime
import ipaddress
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
import db_adapter
from intelligence.intent_engine import IntentEngine
from intelligence.rbac import authorize_request, data_router
from intelligence.response_generator import generate_response
from rag.retriever import retrieve_policy

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder=None)
_local_pending_secret = secrets.token_urlsafe(32)
intent_engine = None
_engine_lock = threading.Lock()


_PRODUCTION_ENVIRONMENTS = {"production", "prod"}


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _environment():
    return os.getenv("VOXERP_ENV", "development").strip().lower()


def _is_production():
    return _environment() in _PRODUCTION_ENVIRONMENTS


def _schema_initialization_enabled():
    """Schema setup is a local-development convenience, never a production action."""
    if _is_production():
        return False
    return _as_bool(
        os.getenv("VOXERP_INITIALIZE_DATABASE"),
        default=False,
    )


def bootstrap_application():
    """Initialize only local development data; production startup is read-only."""
    if _schema_initialization_enabled():
        return db_adapter.initialize_database()
    if db_adapter._real_db_enabled():
        # This issues SELECT 1 only. Do not create or seed database objects here.
        return {"status": "ok" if db_adapter.check_connection() else "error"}
    return {"status": "ok", "message": "Schema initialization disabled"}


# Startup is explicit; importing app never initializes or connects to a database.


def _auth_mode():
    # Production must never accept the development demo identity supplied by a browser.
    if _is_production():
        return "proxy"
    return os.getenv("VOXERP_AUTH_MODE", "demo").strip().lower()


def _trusted_proxy_networks():
    values = os.getenv("VOXERP_TRUSTED_PROXY_CIDRS", "").split(",")
    networks = []
    for value in values:
        value = value.strip()
        if value:
            try:
                networks.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                continue
    return networks


def _request_is_from_trusted_proxy():
    networks = _trusted_proxy_networks()
    if not networks:
        return False
    try:
        address = ipaddress.ip_address(request.remote_addr)
    except (ValueError, TypeError):
        return False
    return any(address in network for network in networks)


def _role_from_groups(groups_header):
    configured = os.getenv(
        "VOXERP_ROLE_GROUPS",
        "voxerp-admins:admin,voxerp-teachers:teacher,voxerp-students:student",
    )
    group_roles = {}
    for mapping in configured.split(","):
        group, separator, role = mapping.partition(":")
        if separator and group.strip() and role.strip():
            group_roles[group.strip().lower()] = role.strip().lower()

    groups = {group.strip().lower() for group in groups_header.split(",") if group.strip()}
    # Privileged group wins if a person belongs to multiple groups.
    for role in ("admin", "teacher", "student"):
        if any(group_roles.get(group) == role for group in groups):
            return role
    return None


def _request_identity(data):
    """Return identity from the configured trust boundary, never mixed sources."""
    if _auth_mode() == "demo":
        if db_adapter._real_db_enabled():
            return None, "Trusted proxy authentication is required for real ERP access."
        user_id = data.get("user_id")
        conn = db_adapter._sqlite_connect()
        try:
            row = conn.execute("SELECT id, role FROM students WHERE id = ?", (user_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            return None, "No valid demo user selected."
        return {"user_id": str(row["id"]), "role": row["role"], "principal_id": str(row["id"])}, None

    if _auth_mode() != "proxy":
        return None, "Server authentication is not configured."
    if not _request_is_from_trusted_proxy():
        return None, "Authentication proxy is required."

    user_id = request.headers.get("X-Forwarded-User", "").strip()
    role = _role_from_groups(request.headers.get("X-Forwarded-Groups", ""))
    # The proxy/IdP supplies this only for students. It avoids relying on demo-user
    # database records to map an authenticated principal to an ERP student record.
    student_id = request.headers.get("X-Forwarded-Student-Id", "").strip()
    if not user_id or not role:
        return None, "Authenticated user does not have a VoxERP role."
    if role == "student" and not student_id:
        return None, "Authenticated student has no ERP identity mapping."
    return {
        "user_id": student_id if role == "student" else user_id,
        "principal_id": user_id,
        "role": role,
    }, None


def _confirmation_serializer():
    secret = os.getenv("VOXERP_PENDING_SECRET", "")
    if not secret and _auth_mode() == "demo" and not db_adapter._real_db_enabled():
        secret = _local_pending_secret
    if not secret:
        return None
    return URLSafeTimedSerializer(secret, salt="voxerp-confirmation")


def _confirmation_token(pending):
    serializer = _confirmation_serializer()
    if serializer is None:
        return None
    return serializer.dumps(pending)


def _load_confirmation_token(token):
    serializer = _confirmation_serializer()
    if serializer is None or not token:
        return None
    try:
        max_age = int(os.getenv("VOXERP_CONFIRMATION_TTL_SECONDS", "300"))
        return serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired, ValueError):
        return None


def _get_intent_engine():
    global intent_engine
    with _engine_lock:
        if intent_engine is None:
            # Use B's existing deterministic mode only for explicit SQLite demos.
            offline = _as_bool(os.getenv("VOXERP_OFFLINE_MODE"))
            if offline and (_is_production() or db_adapter._real_db_enabled()):
                raise RuntimeError("Offline mode is restricted to local SQLite demos")
            intent_engine = IntentEngine(client=object()) if offline else IntentEngine()
        return intent_engine


def parse_intent(text, role):
    return _get_intent_engine().parse(text, role, db_adapter.build_schema_map())


def _json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@app.route("/")
def index():
    return send_from_directory(app.root_path, "index.html")


@app.route("/healthz", methods=["GET"])
def healthz():
    """Read-only health endpoint for the college reverse proxy."""
    available = db_adapter.check_connection()
    return jsonify({"status": "ok" if available else "unavailable"}), 200 if available else 503


@app.route("/me", methods=["GET"])
def current_user():
    """Expose only the already-authenticated identity needed by the web UI."""
    identity, identity_error = _request_identity({})
    if identity_error:
        return jsonify({"error": identity_error}), 401
    return jsonify({"user_id": identity["user_id"], "role": identity["role"]})


@app.route("/users", methods=["GET"])
def list_users():
    """Get list of demo users for the frontend dropdown."""
    if _auth_mode() != "demo":
        return jsonify({"error": "Demo users are disabled when proxy authentication is enabled."}), 404
    if db_adapter._real_db_enabled():
        return jsonify({"error": "Demo users are disabled for real ERP access."}), 404
    conn = None
    try:
        conn = db_adapter._sqlite_connect()
        rows = conn.execute("SELECT id, role, name FROM students ORDER BY id").fetchall()
        return jsonify({"users": [dict(row) for row in rows]})
    except Exception:
        return jsonify({"error": "Failed to fetch users"}), 503
    finally:
        if conn is not None:
            conn.close()


@app.route("/query", methods=["POST"])
def query():
    data = _json_body()
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"reply_text": "Please provide a text request."}), 400
    try:
        identity, error = _request_identity(data)
        if error:
            return jsonify({"reply_text": error}), 401
        intent = parse_intent(text, identity["role"])
        auth = authorize_request(identity["user_id"], identity["role"], intent, text)
        if not auth.get("allowed"):
            return jsonify({"reply_text": generate_response(auth)}), 403
        if data_router.route(intent, text) == "rag":
            return jsonify({"reply_text": generate_response({"policy_context": retrieve_policy(identity["role"], text)})})
        filters = intent.get("filters") or {}
        target = auth["target_student_id"]
        action, table = intent.get("action"), intent.get("table")
        if action == "write" and table == "attendance":
            period = filters.get("period")
            if not filters.get("subject"):
                return jsonify({"reply_text": "Which subject should I mark attendance for?"})
            if isinstance(period, bool) or not isinstance(period, int) or not 1 <= period <= 10:
                return jsonify({"reply_text": "Please specify a period from 1 to 10."})
            pending = {
                "student_id": target, "subject": filters["subject"],
                "date": filters.get("date") or datetime.date.today().isoformat(),
                "status": filters.get("status"), "period": period,
                "actor_id": identity["user_id"], "actor_role": identity["role"],
                "principal_id": identity.get("principal_id", identity["user_id"]),
            }
            token = _confirmation_token(pending)
            if token is None:
                return jsonify({"reply_text": "Confirmation signing is not configured."}), 503
            return jsonify({"reply_text": f"Mark {pending['status']} in {pending['subject']} on {pending['date']}, period {period}. Say yes or no.",
                            "requires_confirmation": True, "confirmation_token": token})
        if action == "read":
            if table == "attendance":
                result = db_adapter.get_attendance(target, filters.get("subject"))
            elif table == "marks":
                result = db_adapter.get_marks(target, filters.get("subject"))
            elif table == "timetable":
                result = db_adapter.get_timetable(target)
            else:
                return jsonify({"reply_text": "Unsupported request."}), 400
            return jsonify({"reply_text": generate_response(result)})
        return jsonify({"reply_text": "Unsupported request."}), 400
    except Exception:
        return jsonify({"reply_text": "Unable to process the request."}), 503


@app.route("/confirm", methods=["POST"])
def confirm():
    data = _json_body()
    try:
        identity, error = _request_identity(data)
        if error:
            return jsonify({"reply_text": error}), 401
        pending = _load_confirmation_token(data.get("confirmation_token"))
        required = {"student_id", "subject", "date", "status", "period", "actor_id", "actor_role"}
        if not isinstance(pending, dict) or not required.issubset(pending):
            return jsonify({"reply_text": "That confirmation has expired or is invalid."}), 400
        if (pending["actor_id"] != identity["user_id"] or pending["actor_role"] != identity["role"]
                or pending.get("principal_id", identity.get("principal_id")) != identity.get("principal_id")):
            return jsonify({"reply_text": "That confirmation belongs to a different user."}), 403
        if data.get("confirm") != "yes":
            return jsonify({"reply_text": "Okay, no changes made."})
        period = pending["period"]
        if isinstance(period, bool) or not isinstance(period, int) or not 1 <= period <= 10:
            return jsonify({"reply_text": "Invalid attendance period."}), 400
        intent = {"action": "write", "table": "attendance", "filters": {
            key: pending[key] for key in ("student_id", "subject", "date", "status", "period")}}
        auth = authorize_request(identity["user_id"], identity["role"], intent)
        if not auth.get("allowed") or str(auth.get("target_student_id")) != str(pending["student_id"]):
            return jsonify({"reply_text": generate_response(auth)}), 403
        if db_adapter._real_db_enabled() and not db_adapter._real_writes_enabled():
            return jsonify({"reply_text": "Real database writes are disabled."})
        result = db_adapter.mark_attendance(pending["student_id"], pending["subject"], pending["date"],
                                           pending["status"], actor_id=identity["user_id"], period=period)
        return jsonify({"reply_text": generate_response(result)})
    except Exception:
        return jsonify({"reply_text": "Unable to process confirmation."}), 503


if __name__ == "__main__":
    if _is_production():
        raise RuntimeError("Use the production WSGI server documented in DEPLOYMENT.md.")
    bootstrap_application()
    app.run(debug=True, port=5050)
