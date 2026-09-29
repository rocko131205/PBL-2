"""TOTP two-factor authentication (RFC 6238 — Google Authenticator, Authy, etc.).

- Secrets are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256).
- Each code can be used once: the accepted time-step is stored and any code
  from the same or an earlier step is rejected (replay protection).
"""
from __future__ import annotations

import io
import time

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from finveritas.security import config

ISSUER = "FinVeritas"
_STEP_SECONDS = 30


def _fernet() -> Fernet:
    return Fernet(config.field_encryption_key())


def new_secret() -> str:
    return pyotp.random_base32()


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def qr_png(uri: str) -> bytes:
    import qrcode

    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def matching_step(secret: str, code: str, *, at: float | None = None) -> int | None:
    """Return the time-step the code belongs to (±1 step drift), or None."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return None
    totp = pyotp.TOTP(secret)
    now = time.time() if at is None else at
    current = int(now // _STEP_SECONDS)
    for step in (current - 1, current, current + 1):
        if totp.verify(code, for_time=step * _STEP_SECONDS):
            return step
    return None


def verify(secret: str, code: str, last_used_step: int | None, *, at: float | None = None) -> int | None:
    """Verify a code and enforce single use. Returns the new step to persist, or None."""
    step = matching_step(secret, code, at=at)
    if step is None:
        return None
    if last_used_step is not None and step <= last_used_step:
        return None  # replayed code
    return step
