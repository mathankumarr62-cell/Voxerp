"""Thin HTTP boundary for VoxERP's authenticated API."""
from __future__ import annotations

import json
import logging
import hashlib
import secrets

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

import db_adapter
from .services import Identity, VoxERPService
from .models import ConsumedConfirmation

logger = logging.getLogger(__name__)
service = VoxERPService()
PENDING_SALT = "voxerp.attendance.confirmation"
PENDING_MAX_AGE_SECONDS = 300


def _json_body(request):
    if len(request.body) > 16_384:
        raise ValueError("Request is too large")
    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON request body") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON object required")
    return payload


def _identity(request) -> Identity:
    """Derive identity only from Django's authenticated user/session."""
    user = request.user
    # ERP student id is intentionally supplied by the authenticated account's username.
    # A deployment can replace this with a protected profile mapping without changing RBAC.
    groups = {name.strip().lower() for name in user.groups.values_list("name", flat=True)}
    if user.is_superuser or "admin" in groups:
        role = "admin"  # Undefined academic permissions: RBAC rejects this role.
    elif "hod" in groups:
        role = "hod"
    else:
        role = "teacher" if "teacher" in groups or user.is_staff else "student"
    return Identity(user_id=user.username, role=role)


@require_GET
@login_required
def users(request):
    # Compatibility endpoint; it never authenticates or authorizes requests.
    return JsonResponse({"users": [{"id": request.user.username, "role": _identity(request).role, "name": request.user.get_full_name() or request.user.username}]})


@require_POST
@login_required
def query(request):
    try:
        payload = _json_body(request)
        response = service.query(_identity(request), payload.get("text", ""))
        status = response.pop("status", 200)
        if response.get("requires_confirmation"):
            response["pending"] = signing.dumps({"user_id": request.user.pk, "nonce": secrets.token_urlsafe(24), "pending": response["pending"]}, salt=PENDING_SALT, compress=True)
        return JsonResponse(response, status=status)
    except ValueError as exc:
        return JsonResponse({"reply_text": str(exc)}, status=400)
    except Exception:
        logger.exception("VoxERP query failed for authenticated user id=%s", request.user.pk)
        return JsonResponse({"reply_text": "Something went wrong on my end, please try again."}, status=500)


@require_POST
@login_required
def confirm(request):
    try:
        payload = _json_body(request)
        decision = str(payload.get("confirm", "")).strip().lower()
        if decision not in {"yes", "no"}:
            return JsonResponse({"reply_text": "Please answer yes or no."}, status=400)
        token = payload.get("pending")
        if not isinstance(token, str):
            return JsonResponse({"reply_text": "I lost track of that request, please try again."}, status=400)
        signed = signing.loads(token, salt=PENDING_SALT, max_age=PENDING_MAX_AGE_SECONDS)
        if signed.get("user_id") != request.user.pk:
            return JsonResponse({"reply_text": "You are not authorized to confirm that request."}, status=403)
        _, first_use = ConsumedConfirmation.objects.get_or_create(
            token_digest=hashlib.sha256(token.encode()).hexdigest()
        )
        if not first_use:
            return JsonResponse({"reply_text": "That confirmation has already been used."}, status=409)
        # Persist consumption before the ERP write, including failed/cancelled attempts.
        response = service.confirm(_identity(request), signed["pending"], decision)
        return JsonResponse({k: v for k, v in response.items() if k != "status"}, status=response["status"])
    except signing.BadSignature:
        return JsonResponse({"reply_text": "That confirmation has expired. Please start again."}, status=400)
    except ValueError as exc:
        return JsonResponse({"reply_text": str(exc)}, status=400)
    except Exception:
        logger.exception("VoxERP confirmation failed for authenticated user id=%s", request.user.pk)
        return JsonResponse({"reply_text": "Something went wrong while saving that, please try again."}, status=500)
