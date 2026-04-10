"""Authentication controller for FinVeritas.

Handles:
- User registration (bcrypt password hashing)
- Login (verify hash → issue JWT)
- Token decode / validation
- OTP generation, email delivery via Gmail SMTP, and verification
- Password reset
"""
from __future__ import annotations

import os
import random
import smtplib
import ssl
import string
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import bcrypt
import jwt
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError

from auth.db import get_users, make_user_doc

load_dotenv()

_JWT_SECRET    = os.getenv("JWT_SECRET", "finveritas-change-this-secret")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_H  = 24  # hours

_SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER = os.getenv("SMTP_USER", "")
_SMTP_PASS = os.getenv("SMTP_PASS", "")


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
    """Register a new user.

    Returns:
        (True, "success") on success
        (False, "<error message>") on failure
    """
    if not all([full_name.strip(), email.strip(), password]):
        return False, "All fields are required."

    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    doc = make_user_doc(full_name.strip(), email.strip(), phone.strip(), state, city, password_hash)

    try:
        get_users().insert_one(doc)
        return True, "success"
    except DuplicateKeyError:
        return False, "An account with this email already exists."
    except Exception as exc:
        return False, f"Registration failed: {exc}"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login_user(email: str, password: str) -> tuple[bool, str | dict]:
    """Validate credentials and issue a JWT.

    Returns:
        (True, jwt_token_string) on success
        (False, "<error message>") on failure
    """
    user = get_users().find_one({"email": email.lower().strip()})
    if not user:
        return False, "No account found with this email."

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return False, "Incorrect password."

    # Update last_login
    get_users().update_one({"_id": user["_id"]}, {"$set": {"last_login": datetime.utcnow()}})

    token = jwt.encode(
        {
            "user_id": str(user["_id"]),
            "email": user["email"],
            "full_name": user["full_name"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=_JWT_EXPIRY_H),
        },
        _JWT_SECRET,
        algorithm=_JWT_ALGORITHM,
    )
    return True, token


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------

def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT. Returns user payload dict or None if invalid/expired."""
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------------------
# OTP — generation, email delivery, verification
# ---------------------------------------------------------------------------

def _generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def _send_otp_email(recipient_email: str, otp: str) -> tuple[bool, str]:
    """Send OTP via Gmail SMTP using App Password.

    Returns (True, "sent") or (False, "<error>").
    """
    if not _SMTP_USER or not _SMTP_PASS:
        return False, "SMTP credentials not configured in .env (SMTP_USER / SMTP_PASS)."

    subject = "FinVeritas — Your Password Reset OTP"
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
                This OTP is valid for <strong style="color:#D4963A;">2 minutes</strong>.<br>
                If you did not request this, please ignore this email.
            </div>
        </div>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = _SMTP_USER
    msg["To"]      = recipient_email
    msg.attach(MIMEText(body_html, "html"))

    try:
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(_SMTP_USER, _SMTP_PASS)
            server.sendmail(_SMTP_USER, recipient_email, msg.as_string())
        return True, "sent"
    except Exception as exc:
        return False, str(exc)


def send_otp(email: str, session_state: Any) -> tuple[bool, str]:
    """Check user exists, generate OTP, send via email, store in session_state.

    Returns (True, "sent") or (False, "<error>").
    """
    user = get_users().find_one({"email": email.lower().strip()})
    if not user:
        return False, "No account found with this email address."

    otp = _generate_otp()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=2)

    session_state["otp_data"] = {
        "email": email.lower().strip(),
        "otp": otp,
        "expiry": expiry,
    }

    ok, msg = _send_otp_email(email, otp)
    return ok, msg


def verify_otp(entered_otp: str, session_state: Any) -> tuple[bool, str]:
    """Verify the entered OTP against what was stored in session_state.

    Returns (True, "verified") or (False, "<reason>").
    """
    otp_data = session_state.get("otp_data")
    if not otp_data:
        return False, "No OTP session found. Please request a new OTP."

    if datetime.now(timezone.utc) > otp_data["expiry"]:
        session_state.pop("otp_data", None)
        return False, "OTP has expired (2-minute limit). Please request a new one."

    if entered_otp.strip() != otp_data["otp"]:
        return False, "Incorrect OTP. Please try again."

    # Mark OTP as verified (keep email, clear otp so it can't be reused)
    session_state["otp_verified_email"] = otp_data["email"]
    session_state.pop("otp_data", None)
    return True, "verified"


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

def reset_password(email: str, new_password: str) -> tuple[bool, str]:
    """Reset a user's password after OTP verification.

    Returns (True, "success") or (False, "<error>").
    """
    if len(new_password) < 8:
        return False, "Password must be at least 8 characters."

    new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    result = get_users().update_one(
        {"email": email.lower().strip()},
        {"$set": {"password_hash": new_hash}},
    )
    if result.matched_count == 0:
        return False, "User not found."
    return True, "success"


# ---------------------------------------------------------------------------
# User lookup helper
# ---------------------------------------------------------------------------

def get_user_by_id(user_id: str) -> dict | None:
    """Fetch a user document by their string ID."""
    from bson import ObjectId
    try:
        return get_users().find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None
