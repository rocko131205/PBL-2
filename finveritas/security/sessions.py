"""Server-side session registry for JWTs.

A bare JWT stays valid until it expires even after the user logs out. Every
token here carries a random `jti` that is registered in the `sessions`
collection; validation checks that the session still exists and is not
revoked, so logout, "sign out everywhere" and password reset take effect
immediately. If the database cannot be reached, validation fails closed.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from finveritas.security import audit, config


def issue(user: dict[str, Any]) -> str:
    """Create a session for `user` and return its signed JWT."""
    from finveritas.auth.db import get_sessions

    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=config.JWT_EXPIRY_HOURS)
    jti = secrets.token_urlsafe(24)
    user_id = str(user["_id"])

    get_sessions().insert_one({
        "jti": jti,
        "user_id": user_id,
        "created_at": now,
        "last_seen": now,  # the API's inactivity timeout counts from here
        "expires_at": exp,
        "revoked": False,
        "ip": audit.client_ip(),
    })
    return jwt.encode(
        {
            "sub": user_id,
            "user_id": user_id,
            "email": user["email"],
            "full_name": user["full_name"],
            "jti": jti,
            "iat": now,
            "exp": exp,
            "iss": config.JWT_ISSUER,
        },
        config.jwt_secret(),
        algorithm=config.JWT_ALGORITHM,
    )


def claims(token: str) -> dict[str, Any] | None:
    """Verify only the token itself (signature, expiry, issuer, required claims) — no database access.

    Callers that go on to check the session record themselves (the API does so atomically with its
    inactivity update) use this instead of `validate` to avoid a second lookup.
    """
    try:
        return jwt.decode(
            token,
            config.jwt_secret(),
            algorithms=[config.JWT_ALGORITHM],  # pinned — rejects alg=none / RS/HS confusion
            issuer=config.JWT_ISSUER,
            options={"require": ["exp", "iat", "jti", "sub", "iss"]},
        )
    except jwt.InvalidTokenError:
        return None


def validate(token: str) -> dict[str, Any] | None:
    """Return the token payload if signature, claims and session are all valid."""
    from finveritas.auth.db import get_sessions

    payload = claims(token)
    if payload is None:
        return None

    try:
        session = get_sessions().find_one({"jti": payload["jti"], "revoked": False})
    except Exception:
        return None  # fail closed
    if not session or session.get("user_id") != payload["sub"]:
        return None
    return payload


def revoke(token: str) -> None:
    """Revoke the session behind `token` (signature must still be valid)."""
    from finveritas.auth.db import get_sessions

    try:
        payload = jwt.decode(
            token, config.jwt_secret(), algorithms=[config.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError:
        return
    get_sessions().update_one({"jti": payload.get("jti")}, {"$set": {"revoked": True}})
    audit.log_event(audit.LOGOUT, email=payload.get("email"), user_id=payload.get("sub"))


def revoke_all(user_id: str, *, except_jti: str | None = None) -> int:
    """Revoke every active session for a user. Returns the number revoked."""
    from finveritas.auth.db import get_sessions

    query: dict[str, Any] = {"user_id": user_id, "revoked": False}
    if except_jti:
        query["jti"] = {"$ne": except_jti}
    result = get_sessions().update_many(query, {"$set": {"revoked": True}})
    audit.log_event(audit.SESSIONS_REVOKED, user_id=user_id, detail={"count": result.modified_count})
    return result.modified_count


def active_count(user_id: str) -> int:
    from finveritas.auth.db import get_sessions

    return get_sessions().count_documents({
        "user_id": user_id, "revoked": False,
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    })
