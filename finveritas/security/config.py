"""Security configuration — secrets are loaded fail-closed.

The app refuses to sign or verify tokens with a missing, short, or well-known
secret instead of silently falling back to a default that is public on GitHub.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from dotenv import load_dotenv

load_dotenv()

# ── Tunables ──────────────────────────────────────────────────────────────────
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 8
JWT_ISSUER = "finveritas"

LOGIN_MAX_FAILURES = 5          # failed logins per account before lockout
LOGIN_WINDOW_MINUTES = 15       # sliding window / lockout duration

OTP_LENGTH = 6
OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 5            # guesses per issued code, then it is burned
OTP_MAX_SENDS = 3               # codes per email per window
OTP_SEND_WINDOW_MINUTES = 15
RESET_GRANT_TTL_MINUTES = 10    # time allowed between OTP verify and password set

MFA_MAX_FAILURES = 5

_MIN_SECRET_LEN = 32
_KNOWN_WEAK_SECRETS = {
    "finveritas-change-this-secret",
    "your_secret",
    "your_super_secret_key",
    "secret",
    "changeme",
}


class SecurityConfigError(RuntimeError):
    """Raised when a required security secret is missing or weak."""


def jwt_secret() -> str:
    """Return JWT_SECRET, or raise if it is missing, short, or a known default."""
    secret = os.getenv("JWT_SECRET", "")
    if not secret or secret in _KNOWN_WEAK_SECRETS or len(secret) < _MIN_SECRET_LEN:
        raise SecurityConfigError(
            f"JWT_SECRET must be set to a random value of at least {_MIN_SECRET_LEN} characters. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return secret


def _derive_key(label: bytes) -> bytes:
    """Derive an independent 32-byte key from JWT_SECRET (HMAC-based KDF)."""
    explicit = os.getenv("FIELD_ENCRYPTION_KEY", "")
    base = explicit if explicit else jwt_secret()
    return hmac.new(base.encode(), label, hashlib.sha256).digest()


def otp_hmac_key() -> bytes:
    return _derive_key(b"finveritas/otp-hash/v1")


def field_encryption_key() -> bytes:
    """URL-safe base64 key for Fernet (used to encrypt TOTP secrets at rest)."""
    return base64.urlsafe_b64encode(_derive_key(b"finveritas/field-encryption/v1"))


def validate_startup() -> list[str]:
    """Return a list of fatal configuration problems (empty = OK)."""
    problems: list[str] = []
    try:
        jwt_secret()
    except SecurityConfigError as exc:
        problems.append(str(exc))
    return problems
