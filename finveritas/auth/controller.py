"""Authentication controller for FinVeritas.

Handles:
- User registration (bcrypt hashing + server-side password policy)
- Login with account lockout, generic errors and timing equalisation
- Optional TOTP second factor
- Server-side JWT sessions (revocable on logout / password reset)
- Password reset via single-use, attempt-limited, hashed email OTP
- Security audit logging for every step

See docs/security/PENTEST_REPORT.md for the findings these controls address.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import smtplib
import ssl
import sys
import threading
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import bcrypt
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError

from finveritas.auth.db import get_password_resets, get_users, make_user_doc
from finveritas.security import audit, config, mfa, ratelimit, sessions
from finveritas.security.passwords import password_issues

load_dotenv()

_SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER = os.getenv("SMTP_USER", "")
_SMTP_PASS = os.getenv("SMTP_PASS", "")

GENERIC_LOGIN_ERROR = "Invalid email or password."
GENERIC_OTP_SENT = "If an account exists for that email, a code has been sent. It is valid for 5 minutes."
GENERIC_OTP_ERROR = "Invalid or expired code."

_dummy_hash: bytes | None = None


def _normalize_email(email: str) -> str:
    return (email or "").lower().strip()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _burn_bcrypt_time(password: str) -> None:
    """Run a bcrypt check against a throwaway hash so unknown emails take as long as known ones."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt())
    bcrypt.checkpw(password.encode()[:72], _dummy_hash)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_user(
    full_name: str,
    email: str,
    phone: str,
    state: str,
    city: str,
    password: str,
) -> tuple[bool, str]:
    """Register a new user. Returns (True, "success") or (False, "<error>")."""
    if not all([full_name.strip(), email.strip(), password]):
        return False, "All fields are required."

    issues = password_issues(password)
    if issues:
        return False, "Password needs: " + ", ".join(issues)

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    doc = make_user_doc(full_name.strip(), email.strip(), phone.strip(), state, city, password_hash)

    try:
        result = get_users().insert_one(doc)
    except DuplicateKeyError:
        # Accepted residual risk: registration reveals existing emails (see THREAT_MODEL.md).
        return False, "An account with this email already exists."
    except Exception as exc:
        print(f"[auth] registration error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return False, "Registration failed due to a server error. Please try again later."

    audit.log_event(audit.REGISTER, email=doc["email"], user_id=str(result.inserted_id))
    return True, "success"


# ---------------------------------------------------------------------------
# Login (+ optional MFA)
# ---------------------------------------------------------------------------

def _login_key(email: str) -> str:
    return f"login:{email}"


def login_user(email: str, password: str) -> tuple[bool, str | dict]:
    """Validate credentials.

    Returns:
        (True, jwt_token)                                  — signed in
        (True, {"mfa_required": True, "user_id": "..."})   — password OK, TOTP needed
        (False, "<generic error>")
    """
    email = _normalize_email(email)
    key = _login_key(email)

    if ratelimit.is_limited(key, config.LOGIN_MAX_FAILURES, config.LOGIN_WINDOW_MINUTES):
        wait = ratelimit.retry_after_minutes(key, config.LOGIN_WINDOW_MINUTES)
        audit.log_event(audit.LOGIN_LOCKED, email=email)
        return False, f"Too many failed attempts. Try again in {wait} minute(s)."

    user = get_users().find_one({"email": email})
    if not user:
        _burn_bcrypt_time(password)
        ratelimit.record(key, config.LOGIN_WINDOW_MINUTES)
        audit.log_event(audit.LOGIN_FAILURE, email=email, detail={"reason": "unknown_email"})
        return False, GENERIC_LOGIN_ERROR

    if not bcrypt.checkpw(password.encode()[:72], user["password_hash"].encode()):
        ratelimit.record(key, config.LOGIN_WINDOW_MINUTES)
        audit.log_event(audit.LOGIN_FAILURE, email=email, user_id=str(user["_id"]),
                        detail={"reason": "bad_password"})
        return False, GENERIC_LOGIN_ERROR

    if user.get("mfa_enabled"):
        return True, {"mfa_required": True, "user_id": str(user["_id"])}

    return True, _finish_login(user)


def complete_mfa_login(user_id: str, code: str) -> tuple[bool, str]:
    """Second step of login for MFA-enabled accounts. Returns (True, jwt) or (False, error)."""
    from bson import ObjectId

    key = f"mfa:{user_id}"
    if ratelimit.is_limited(key, config.MFA_MAX_FAILURES, config.LOGIN_WINDOW_MINUTES):
        audit.log_event(audit.LOGIN_LOCKED, user_id=user_id, detail={"stage": "mfa"})
        return False, "Too many incorrect codes. Please wait and sign in again."

    try:
        user = get_users().find_one({"_id": ObjectId(user_id)})
    except Exception:
        user = None
    if not user or not user.get("mfa_enabled"):
        return False, "Session expired. Please sign in again."

    secret = mfa.decrypt_secret(user.get("mfa_secret_enc") or "")
    step = mfa.verify(secret, code, user.get("mfa_last_step")) if secret else None
    if step is None:
        ratelimit.record(key, config.LOGIN_WINDOW_MINUTES)
        audit.log_event(audit.MFA_FAILURE, email=user["email"], user_id=user_id)
        return False, "Invalid authentication code."

    # Conditional update: a concurrent request with the same code cannot also succeed.
    res = get_users().update_one(
        {"_id": user["_id"], "mfa_last_step": user.get("mfa_last_step")},
        {"$set": {"mfa_last_step": step}},
    )
    if res.modified_count != 1:
        return False, "Invalid authentication code."
    ratelimit.clear(key)
    return True, _finish_login(user)


def _finish_login(user: dict[str, Any]) -> str:
    ratelimit.clear(_login_key(user["email"]))
    get_users().update_one({"_id": user["_id"]}, {"$set": {"last_login": _utcnow()}})
    token = sessions.issue(user)
    audit.log_event(audit.LOGIN_SUCCESS, email=user["email"], user_id=str(user["_id"]),
                    detail={"mfa": bool(user.get("mfa_enabled"))})
    return token


def logout(token: str | None) -> None:
    if token:
        sessions.revoke(token)


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------

def decode_token(token: str) -> dict[str, Any] | None:
    """Validate a JWT and its server-side session. Returns the payload or None."""
    return sessions.validate(token)


# ---------------------------------------------------------------------------
# MFA enrolment
# ---------------------------------------------------------------------------

def begin_mfa_enrolment(user_id: str) -> tuple[str, str]:
    """Return (secret, provisioning_uri) for a new TOTP enrolment. Nothing is saved yet."""
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("User not found.")
    secret = mfa.new_secret()
    return secret, mfa.provisioning_uri(secret, user["email"])


def confirm_mfa_enrolment(user_id: str, secret: str, code: str) -> tuple[bool, str]:
    """Enable MFA once the user proves their authenticator produces valid codes."""
    step = mfa.verify(secret, code, None)
    if step is None:
        return False, "That code didn't match. Check your device's clock and try again."
    user = get_user_by_id(user_id)
    if not user:
        return False, "User not found."
    get_users().update_one({"_id": user["_id"]}, {"$set": {
        "mfa_enabled": True,
        "mfa_secret_enc": mfa.encrypt_secret(secret),
        "mfa_last_step": step,
    }})
    audit.log_event(audit.MFA_ENABLED, email=user["email"], user_id=user_id)
    return True, "Two-factor authentication is now enabled."


def disable_mfa(user_id: str, code: str) -> tuple[bool, str]:
    """Disabling MFA requires a current code, so a hijacked session alone can't remove it."""
    user = get_user_by_id(user_id)
    if not user or not user.get("mfa_enabled"):
        return False, "Two-factor authentication is not enabled."
    secret = mfa.decrypt_secret(user.get("mfa_secret_enc") or "")
    step = mfa.verify(secret, code, user.get("mfa_last_step")) if secret else None
    if step is None:
        audit.log_event(audit.MFA_FAILURE, email=user["email"], user_id=user_id, detail={"stage": "disable"})
        return False, "Invalid authentication code."
    get_users().update_one({"_id": user["_id"]}, {"$set": {
        "mfa_enabled": False, "mfa_secret_enc": None, "mfa_last_step": None,
    }})
    audit.log_event(audit.MFA_DISABLED, email=user["email"], user_id=user_id)
    return True, "Two-factor authentication has been disabled."


# ---------------------------------------------------------------------------
# Password reset — OTP generation, delivery, verification
# ---------------------------------------------------------------------------

def _generate_otp(length: int = config.OTP_LENGTH) -> str:
    """Cryptographically secure numeric code (the `random` module is predictable)."""
    return f"{secrets.randbelow(10 ** length):0{length}d}"


def _hash_otp(email: str, otp: str) -> str:
    """Keyed hash so a database leak does not reveal live codes."""
    return hmac.new(config.otp_hmac_key(), f"{email}:{otp}".encode(), hashlib.sha256).hexdigest()


def _smtp_configured() -> bool:
    return bool(_SMTP_USER and _SMTP_PASS)


def _send_otp_email(recipient_email: str, otp: str) -> tuple[bool, str]:
    """Send OTP via SMTP with STARTTLS and full certificate verification."""
    if not _smtp_configured():
        return False, "SMTP credentials not configured in .env (SMTP_USER / SMTP_PASS)."

    subject = "FinVeritas — Your Password Reset Code"
    body_html = f"""
    <html><body style="font-family: 'Courier New', monospace; background: #0A0B0E; color: #D8D8E0; padding: 32px;">
        <div style="max-width:480px; margin:0 auto; background:#10121A; border:1px solid #1E2030;
                    border-left:4px solid #D4963A; border-radius:4px; padding:28px;">
            <div style="font-size:20px; font-weight:700; color:#D4963A; letter-spacing:0.12em; margin-bottom:6px;">
                FV FinVeritas
            </div>
            <div style="font-size:11px; color:#5A5A72; letter-spacing:0.18em; margin-bottom:24px;">
                EXPLAINABLE FINANCIAL ANALYSIS PLATFORM
            </div>
            <div style="font-size:13px; color:#9A9AB0; margin-bottom:16px;">
                Your one-time password (OTP) for account recovery:
            </div>
            <div style="font-size:40px; font-weight:700; color:#D4963A; letter-spacing:0.3em;
                        background:#0A0B0E; padding:16px 24px; border-radius:2px;
                        border:1px solid #D4963A22; text-align:center; margin-bottom:20px;">
                {otp}
            </div>
            <div style="font-size:11px; color:#5A5A72;">
                This code is valid for <strong style="color:#D4963A;">{config.OTP_TTL_MINUTES} minutes</strong>
                and can be used once.<br>
                If you did not request this, you can ignore this email — your password has not changed.
            </div>
        </div>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _SMTP_USER
    msg["To"] = recipient_email
    msg.attach(MIMEText(body_html, "html"))

    try:
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            context = ssl.create_default_context()  # system trust store — never disable verification
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(_SMTP_USER, _SMTP_PASS)
            server.sendmail(_SMTP_USER, recipient_email, msg.as_string())
        return True, "sent"
    except Exception as exc:
        return False, f"{type(exc).__name__}"


def _deliver_async(email: str, otp: str) -> None:
    """Send in the background so response time doesn't reveal whether the account exists."""
    def _run() -> None:
        ok, err = _send_otp_email(email, otp)
        if not ok:
            print(f"[auth] OTP email delivery failed: {err}", file=sys.stderr)
    threading.Thread(target=_run, daemon=True).start()


def send_otp(email: str, session_state: Any) -> tuple[bool, str]:
    """Issue a reset code. The response is identical whether or not the account exists."""
    email = _normalize_email(email)
    if not _smtp_configured():
        # Configuration problem — independent of the email, so it reveals nothing.
        return False, "Password reset by email is not configured on this server."

    send_key = f"otp_send:{email}"
    if ratelimit.is_limited(send_key, config.OTP_MAX_SENDS, config.OTP_SEND_WINDOW_MINUTES):
        audit.log_event(audit.OTP_THROTTLED, email=email)
        return False, "Too many reset requests. Please wait before trying again."
    ratelimit.record(send_key, config.OTP_SEND_WINDOW_MINUTES)

    session_state["otp_email"] = email
    user = get_users().find_one({"email": email})
    if user:
        otp = _generate_otp()
        now = _utcnow()
        # One live code per account: a new request replaces (invalidates) the old one.
        get_password_resets().replace_one(
            {"email": email},
            {
                "email": email,
                "otp_hash": _hash_otp(email, otp),
                "created_at": now,
                "expires_at": now + timedelta(minutes=config.OTP_TTL_MINUTES),
                "attempts": 0,
            },
            upsert=True,
        )
        _deliver_async(email, otp)
        audit.log_event(audit.OTP_REQUESTED, email=email, user_id=str(user["_id"]))
    else:
        audit.log_event(audit.OTP_REQUESTED, email=email, detail={"account_exists": False})
    return True, GENERIC_OTP_SENT


def verify_otp(entered_otp: str, session_state: Any) -> tuple[bool, str]:
    """Check a reset code: constant-time compare, max attempts, single use, expiry."""
    email = session_state.get("otp_email")
    if not email:
        return False, "No reset in progress. Please request a new code."

    resets = get_password_resets()
    record = resets.find_one({"email": email})
    if not record or _aware(record["expires_at"]) < _utcnow():
        audit.log_event(audit.OTP_FAILURE, email=email, detail={"reason": "missing_or_expired"})
        return False, GENERIC_OTP_ERROR

    # Count the attempt *before* comparing, atomically, so parallel guesses can't exceed the cap.
    record = resets.find_one_and_update(
        {"_id": record["_id"], "attempts": {"$lt": config.OTP_MAX_ATTEMPTS}},
        {"$inc": {"attempts": 1}},
    )
    if not record:
        resets.delete_one({"email": email})
        audit.log_event(audit.OTP_FAILURE, email=email, detail={"reason": "attempts_exhausted"})
        return False, "Too many incorrect attempts. Please request a new code."

    candidate = _hash_otp(email, (entered_otp or "").strip())
    if not hmac.compare_digest(candidate, record["otp_hash"]):
        remaining = config.OTP_MAX_ATTEMPTS - (record["attempts"] + 1)
        audit.log_event(audit.OTP_FAILURE, email=email, detail={"reason": "mismatch", "remaining": remaining})
        if remaining <= 0:
            resets.delete_one({"email": email})
            return False, "Too many incorrect attempts. Please request a new code."
        return False, f"{GENERIC_OTP_ERROR} {remaining} attempt(s) left."

    resets.delete_one({"email": email})  # single use
    session_state["reset_grant"] = {
        "email": email,
        "expires": _utcnow() + timedelta(minutes=config.RESET_GRANT_TTL_MINUTES),
    }
    session_state.pop("otp_email", None)
    audit.log_event(audit.OTP_VERIFIED, email=email)
    return True, "verified"


def complete_password_reset(session_state: Any, new_password: str) -> tuple[bool, str]:
    """Set a new password using the short-lived grant created by verify_otp."""
    grant = session_state.get("reset_grant")
    if not grant or _aware(grant["expires"]) < _utcnow():
        session_state.pop("reset_grant", None)
        return False, "Your reset session expired. Please start again."
    ok, msg = reset_password(grant["email"], new_password)
    if ok:
        session_state.pop("reset_grant", None)
    return ok, msg


def reset_password(email: str, new_password: str) -> tuple[bool, str]:
    """Low-level password change. Callers must have verified the user first."""
    issues = password_issues(new_password)
    if issues:
        return False, "Password needs: " + ", ".join(issues)

    email = _normalize_email(email)
    new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(rounds=12)).decode()
    user = get_users().find_one_and_update({"email": email}, {"$set": {"password_hash": new_hash}})
    if not user:
        return False, "User not found."

    # A reset usually means the old password may be compromised: end every session.
    sessions.revoke_all(str(user["_id"]))
    ratelimit.clear(_login_key(email))
    audit.log_event(audit.PASSWORD_RESET, email=email, user_id=str(user["_id"]))
    return True, "success"


# ---------------------------------------------------------------------------
# User lookup helpers
# ---------------------------------------------------------------------------

def get_user_by_id(user_id: str) -> dict | None:
    """Fetch a user document by their string ID."""
    from bson import ObjectId
    try:
        return get_users().find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


def is_admin(user_id: str) -> bool:
    """Role is read from the database on every check so a demotion applies immediately."""
    user = get_user_by_id(user_id)
    return bool(user and user.get("role") == "admin")
