"""Request-scoped dependencies: cookie sessions, CSRF, inactivity timeout, admin gate."""
from __future__ import annotations

import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, Response

from finveritas.auth.controller import is_admin
from finveritas.auth.db import get_sessions
from finveritas.security import audit, config
from finveritas.security.sessions import claims as session_claims

SESSION_COOKIE = "fv_session"
CSRF_COOKIE = "fv_csrf"
CSRF_HEADER = "x-csrf-token"
INACTIVITY_MINUTES = 15
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _secure_cookies() -> bool:
    # Browsers treat http://localhost as a secure context, so this is safe to leave on in dev too.
    return os.getenv("COOKIE_SECURE", "true").lower() not in {"0", "false", "no"}


def set_session_cookies(response: Response, token: str) -> None:
    max_age = config.JWT_EXPIRY_HOURS * 3600
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True,
                        secure=_secure_cookies(), samesite="strict", path="/")
    # Readable by the SPA so it can echo the value in a header (double-submit CSRF defence).
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(24), max_age=max_age, httponly=False,
                        secure=_secure_cookies(), samesite="strict", path="/")


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _check_csrf(request: Request) -> None:
    if request.method not in _UNSAFE:
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        audit.log_event(audit.TOKEN_REJECTED, detail={"reason": "csrf", "path": request.url.path})
        raise HTTPException(403, "CSRF check failed.")


def _touch_session(claims: dict[str, Any]) -> bool:
    """Confirm the session is live and record activity, in ONE atomic database call.

    Matches only if the session exists, belongs to the token's user, isn't revoked, and was active
    within the inactivity window. False = revoked, unknown or timed out.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=INACTIVITY_MINUTES)
    sessions = get_sessions()
    try:
        hit = sessions.find_one_and_update(
            {
                "jti": claims["jti"], "user_id": claims["sub"], "revoked": False,
                # Sessions created before last_seen existed fall back to their creation time.
                "$or": [{"last_seen": {"$gte": cutoff}},
                        {"last_seen": {"$exists": False}, "created_at": {"$gte": cutoff}}],
            },
            {"$set": {"last_seen": now}},
            projection={"_id": 1},
        )
    except Exception:
        return False  # fail closed if the database can't be reached
    if hit:
        return True
    # Not matched: if it was merely idle too long, end it for good (cheap, and only on this rare path).
    sessions.update_one({"jti": claims["jti"], "revoked": False}, {"$set": {"revoked": True}})
    return False


def current_user(request: Request) -> dict[str, Any]:
    """The authenticated user's token payload, or 401. Revocation is checked on every request."""
    token = request.cookies.get(SESSION_COOKIE)
    user = session_claims(token) if token else None
    if not user or not _touch_session(user):
        raise HTTPException(401, "Not authenticated.")
    _check_csrf(request)
    audit.set_client_ip(client_ip(request))
    return user


def admin_only(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    """Authorisation is re-checked against the database on every call."""
    if not is_admin(user["user_id"]):
        audit.log_event(audit.AUTHZ_DENIED, user_id=user["user_id"], detail={"area": "admin"})
        raise HTTPException(403, "You do not have permission to view this.")
    return user


def _trusted_hops() -> int:
    try:
        return max(0, int(os.getenv("TRUST_PROXY_HOPS", "0")))
    except ValueError:
        return 0


def client_ip(request: Request) -> str | None:
    """The real client address.

    X-Forwarded-For is only meaningful behind proxies you run, and a client can put anything at the
    front of it. So it is ignored unless TRUST_PROXY_HOPS says how many trusted proxies sit in front
    of the app (1 on Render); then the entry those proxies appended — counted from the END — is used.
    """
    hops = _trusted_hops()
    forwarded = request.headers.get("x-forwarded-for")
    if hops and forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else None
