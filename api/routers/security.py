"""Security Settings (per user) and the admin Security Dashboard."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api import tokens
from api.deps import admin_only, current_user
from finveritas.auth.controller import begin_mfa_enrolment, confirm_mfa_enrolment, disable_mfa, get_user_by_id
from finveritas.auth.db import get_audit_log, get_sessions
from finveritas.security import audit, mfa, sessions

router = APIRouter(prefix="/api", tags=["security"])

PURPOSE_MFA_ENROL = "mfa_enrol"
ENROL_MINUTES = 10


def _event(e: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": e.get("timestamp"),
        "event": e.get("event", ""),
        "outcome": e.get("outcome", ""),
        "email": e.get("email") or "",
        "ip": e.get("ip") or "",
        "detail": ", ".join(f"{k}={v}" for k, v in (e.get("detail") or {}).items()),
    }


# ── Per-user settings ────────────────────────────────────────────────────────

@router.get("/security")
def overview(user: dict = Depends(current_user)) -> dict[str, Any]:
    db_user = get_user_by_id(user["user_id"]) or {}
    events = audit.recent_events(user_id=user["user_id"], email=db_user.get("email"), limit=25)
    return {
        "mfa_enabled": bool(db_user.get("mfa_enabled")),
        "active_sessions": sessions.active_count(user["user_id"]),
        "activity": [_event(e) for e in events],
    }


@router.post("/security/mfa/begin")
def mfa_begin(user: dict = Depends(current_user)) -> dict[str, str]:
    db_user = get_user_by_id(user["user_id"]) or {}
    if db_user.get("mfa_enabled"):
        raise HTTPException(400, "Two-factor authentication is already enabled.")
    secret, uri = begin_mfa_enrolment(user["user_id"])
    return {
        "secret": secret,
        "qr_png": base64.b64encode(mfa.qr_png(uri)).decode(),
        # Binds the pending secret to this user for a few minutes; nothing is saved until confirmed.
        "enrol_token": tokens.issue(PURPOSE_MFA_ENROL, user["user_id"], ENROL_MINUTES, secret=secret),
    }


class ConfirmIn(BaseModel):
    enrol_token: str
    code: str = Field(max_length=10)


@router.post("/security/mfa/confirm")
def mfa_confirm(body: ConfirmIn, user: dict = Depends(current_user)) -> dict[str, str]:
    claims = tokens.read(body.enrol_token, PURPOSE_MFA_ENROL)
    if not claims or claims["sub"] != user["user_id"]:
        raise HTTPException(400, "This setup session expired. Please start again.")
    ok, msg = confirm_mfa_enrolment(user["user_id"], claims["secret"], body.code.strip())
    if not ok:
        raise HTTPException(400, msg)
    return {"message": msg}


class CodeIn(BaseModel):
    code: str = Field(max_length=10)


@router.post("/security/mfa/disable")
def mfa_disable(body: CodeIn, user: dict = Depends(current_user)) -> dict[str, str]:
    ok, msg = disable_mfa(user["user_id"], body.code.strip())
    if not ok:
        raise HTTPException(400, msg)
    return {"message": msg}


@router.post("/security/sessions/revoke-others")
def revoke_others(user: dict = Depends(current_user)) -> dict[str, int]:
    return {"revoked": sessions.revoke_all(user["user_id"], except_jti=user.get("jti"))}


# ── Admin dashboard ──────────────────────────────────────────────────────────

@router.get("/admin/security")
def dashboard(failures_only: bool = True, _: dict = Depends(admin_only)) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    log = get_audit_log()

    def n(event: str) -> int:
        return log.count_documents({"event": event, "timestamp": {"$gte": since}})

    top_accounts = log.aggregate([
        {"$match": {"event": audit.LOGIN_FAILURE, "timestamp": {"$gte": since}}},
        {"$group": {"_id": "$email", "failures": {"$sum": 1}, "ips": {"$addToSet": "$ip"}}},
        {"$sort": {"failures": -1}}, {"$limit": 10},
    ])
    top_ips = log.aggregate([
        {"$match": {"outcome": "failure", "timestamp": {"$gte": since}, "ip": {"$ne": None}}},
        {"$group": {"_id": "$ip", "events": {"$sum": 1}, "accounts": {"$addToSet": "$email"}}},
        {"$sort": {"events": -1}}, {"$limit": 10},
    ])
    events = log.find({"outcome": "failure"} if failures_only else {}).sort("timestamp", -1).limit(200)
    return {
        "counts": {
            "login_success": n(audit.LOGIN_SUCCESS), "login_failure": n(audit.LOGIN_FAILURE),
            "lockouts": n(audit.LOGIN_LOCKED), "otp_failures": n(audit.OTP_FAILURE),
            "prompt_injection": n(audit.PROMPT_INJECTION),
        },
        "active_sessions": get_sessions().count_documents({"revoked": False, "expires_at": {"$gt": now}}),
        "top_accounts": [{"email": t["_id"], "failures": t["failures"], "distinct_ips": len([i for i in t["ips"] if i])}
                         for t in top_accounts],
        "top_ips": [{"ip": t["_id"], "events": t["events"], "accounts": len([a for a in t["accounts"] if a])}
                    for t in top_ips],
        "events": [_event(e) for e in events],
    }
