"""Append-only security audit log (MongoDB `audit_log` collection).

Every authentication-relevant event is recorded with who, what, when and from
where. Logging never raises: a logging failure must not break sign-in, but it
is reported on stderr so it is not silent.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

# Event names — kept as constants so dashboards and tests agree on spelling.
LOGIN_SUCCESS = "login_success"
LOGIN_FAILURE = "login_failure"
LOGIN_LOCKED = "login_locked"
LOGOUT = "logout"
REGISTER = "register"
MFA_ENABLED = "mfa_enabled"
MFA_DISABLED = "mfa_disabled"
MFA_FAILURE = "mfa_failure"
OTP_REQUESTED = "otp_requested"
OTP_THROTTLED = "otp_throttled"
OTP_FAILURE = "otp_failure"
OTP_VERIFIED = "otp_verified"
PASSWORD_RESET = "password_reset"
SESSIONS_REVOKED = "sessions_revoked"
UPLOAD_REJECTED = "upload_rejected"
PROMPT_INJECTION = "prompt_injection_detected"
TOKEN_REJECTED = "token_rejected"
AUTHZ_DENIED = "authz_denied"

_FAILURE_EVENTS = {
    LOGIN_FAILURE, LOGIN_LOCKED, MFA_FAILURE, OTP_THROTTLED, OTP_FAILURE,
    UPLOAD_REJECTED, PROMPT_INJECTION, TOKEN_REJECTED, AUTHZ_DENIED,
}


def client_ip() -> str | None:
    """Best-effort client IP from the active Streamlit request."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx(suppress_warning=True) is None:
            return None
        import streamlit as st
        return getattr(st.context, "ip_address", None)
    except Exception:
        return None


def log_event(
    event: str,
    *,
    email: str | None = None,
    user_id: str | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Record a security event. Never raises."""
    from finveritas.auth.db import get_audit_log

    doc = {
        "event": event,
        "outcome": "failure" if event in _FAILURE_EVENTS else "success",
        "email": email.lower().strip() if email else None,
        "user_id": user_id,
        "ip": ip if ip is not None else client_ip(),
        "detail": detail or {},
        "timestamp": datetime.now(timezone.utc),
    }
    try:
        get_audit_log().insert_one(doc)
    except Exception as exc:  # pragma: no cover - depends on DB availability
        print(f"[audit] failed to record {event}: {type(exc).__name__}", file=sys.stderr)


def recent_events(*, user_id: str | None = None, email: str | None = None, limit: int = 50) -> list[dict]:
    """Most recent events, optionally filtered to one user."""
    from finveritas.auth.db import get_audit_log

    query: dict[str, Any] = {}
    if user_id or email:
        ors = []
        if user_id:
            ors.append({"user_id": user_id})
        if email:
            ors.append({"email": email.lower().strip()})
        query["$or"] = ors
    return list(get_audit_log().find(query).sort("timestamp", -1).limit(limit))
