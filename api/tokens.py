"""Short-lived signed tokens for multi-step flows (MFA login, password reset).

These replace the values Streamlit kept in `st.session_state` between steps. Each
token carries a `purpose` claim so one can never be replayed as another, and is
signed with a key derived from JWT_SECRET (never the raw session-signing key).
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import jwt

from finveritas.security import config

PURPOSE_MFA = "mfa"
PURPOSE_RESET = "reset"
_ISSUER = "finveritas-flow"


def _key() -> str:
    return hmac.new(config.jwt_secret().encode(), b"finveritas/flow-token/v1", hashlib.sha256).hexdigest()


def issue(purpose: str, subject: str, minutes: int, **claims: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"purpose": purpose, "sub": subject, "iat": now, "exp": now + timedelta(minutes=minutes),
         "iss": _ISSUER, **claims},
        _key(), algorithm="HS256",
    )


def read(token: str, purpose: str) -> dict | None:
    """Return the claims if the token is valid, unexpired and made for `purpose`."""
    try:
        claims = jwt.decode(token, _key(), algorithms=["HS256"], issuer=_ISSUER,
                            options={"require": ["exp", "iat", "sub", "purpose"]})
    except jwt.InvalidTokenError:
        return None
    return claims if claims.get("purpose") == purpose else None


def password_fingerprint(password_hash: str) -> str:
    """Changes whenever the password does, which makes a reset token single-use."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:24]
