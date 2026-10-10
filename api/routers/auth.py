"""Sign-up, sign-in (+MFA), sign-out and password reset."""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from api import tokens
from api.deps import SESSION_COOKIE, clear_session_cookies, current_user, set_session_cookies
from finveritas.auth import controller
from finveritas.auth.states import ALL_STATES, STATES_AND_CITIES, get_cities

router = APIRouter(prefix="/api", tags=["auth"])

_NAME_RE = re.compile(r"^[A-Za-z\s.\-']+$")
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_COUNTRY_CODE_RE = re.compile(r"^\+\d{1,3}$")

MFA_TOKEN_MINUTES = 5
RESET_TOKEN_MINUTES = 10


class RegisterIn(BaseModel):
    full_name: str = Field(max_length=100)
    email: str = Field(max_length=254)
    country_code: str = "+91"
    phone: str = Field(max_length=20)
    state: str
    city: str
    password: str = Field(max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class MfaIn(BaseModel):
    mfa_token: str
    code: str = Field(max_length=10)


class EmailIn(BaseModel):
    email: str = Field(max_length=254)


class VerifyOtpIn(BaseModel):
    email: str = Field(max_length=254)
    code: str = Field(max_length=10)


class ResetIn(BaseModel):
    reset_token: str
    new_password: str = Field(max_length=200)


def _public_user(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": payload["user_id"],
        "email": payload["email"],
        "full_name": payload["full_name"],
        "is_admin": controller.is_admin(payload["user_id"]),
    }


def _registration_errors(body: RegisterIn) -> dict[str, str]:
    """Server-side mirror of the form rules (the browser's checks are only a convenience)."""
    errors: dict[str, str] = {}
    name = body.full_name.strip()
    if len(name) < 2:
        errors["full_name"] = "Full name must be at least 2 characters."
    elif not _NAME_RE.match(name):
        errors["full_name"] = "Full name may only contain letters, spaces, hyphens, dots or apostrophes."
    if not _EMAIL_RE.match(body.email.strip()):
        errors["email"] = "Please enter a valid email address."
    if not _COUNTRY_CODE_RE.match(body.country_code):
        errors["country_code"] = "Invalid country code."
    if len(re.sub(r"\D", "", body.phone)) != 10:
        errors["phone"] = "Phone number must be exactly 10 digits."
    if body.state not in STATES_AND_CITIES:
        errors["state"] = "Please select your state."
    elif body.city not in STATES_AND_CITIES[body.state]:
        errors["city"] = "Please select your city."
    return errors


# ── Reference data ───────────────────────────────────────────────────────────

@router.get("/geo/states")
def states() -> list[str]:
    return ALL_STATES


@router.get("/geo/cities")
def cities(state: str) -> list[str]:
    return get_cities(state)


# ── Registration / sign-in ───────────────────────────────────────────────────

@router.post("/auth/register", status_code=201)
def register(body: RegisterIn) -> dict[str, str]:
    errors = _registration_errors(body)
    if errors:
        raise HTTPException(422, detail={"errors": errors})
    digits = re.sub(r"\D", "", body.phone)
    phone = f"{body.country_code}{digits}"
    ok, msg = controller.register_user(
        full_name=body.full_name.strip(), email=body.email.strip(), phone=phone,
        state=body.state, city=body.city, password=body.password,
    )
    if not ok:
        raise HTTPException(409 if "already exists" in msg else 400, msg)
    return {"status": "created"}


@router.post("/auth/login")
def login(body: LoginIn, response: Response) -> dict[str, Any]:
    if not body.email.strip() or not body.password:
        raise HTTPException(400, "Please enter both email and password.")
    ok, result = controller.login_user(body.email.strip(), body.password)
    if not ok:
        raise HTTPException(429 if "Too many" in str(result) else 401, str(result))
    if isinstance(result, dict) and result.get("mfa_required"):
        return {"mfa_required": True,
                "mfa_token": tokens.issue(tokens.PURPOSE_MFA, result["user_id"], MFA_TOKEN_MINUTES)}
    set_session_cookies(response, result)
    return {"mfa_required": False, "user": _public_user(controller.decode_token(result))}


@router.post("/auth/login/mfa")
def login_mfa(body: MfaIn, response: Response) -> dict[str, Any]:
    claims = tokens.read(body.mfa_token, tokens.PURPOSE_MFA)
    if not claims:
        raise HTTPException(401, "Session expired. Please sign in again.")
    ok, result = controller.complete_mfa_login(claims["sub"], body.code.strip())
    if not ok:
        raise HTTPException(429 if "Too many" in result else 401, result)
    set_session_cookies(response, result)
    return {"user": _public_user(controller.decode_token(result))}


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    # Allowed without a valid session so a stale tab can always clear its cookies.
    controller.logout(request.cookies.get(SESSION_COOKIE))
    clear_session_cookies(response)
    return {"status": "signed_out"}


@router.get("/auth/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return _public_user(user)


# ── Password reset: email -> code -> new password ────────────────────────────

@router.post("/password-reset/send-otp")
def send_otp(body: EmailIn) -> dict[str, str]:
    ok, msg = controller.send_otp(body.email, {})
    if not ok:
        raise HTTPException(429 if "Too many" in msg else 503, msg)
    return {"message": msg}


@router.post("/password-reset/verify-otp")
def verify_otp(body: VerifyOtpIn) -> dict[str, str]:
    email = controller._normalize_email(body.email)
    ok, msg = controller.verify_otp(body.code, {"otp_email": email})
    if not ok:
        raise HTTPException(400, msg)
    user = controller.get_users().find_one({"email": email})
    if not user:  # cannot happen after a verified code, but never mint a token without an account
        raise HTTPException(400, controller.GENERIC_OTP_ERROR)
    return {"reset_token": tokens.issue(
        tokens.PURPOSE_RESET, email, RESET_TOKEN_MINUTES,
        pwf=tokens.password_fingerprint(user["password_hash"]),
    )}


@router.post("/password-reset/reset")
def reset(body: ResetIn) -> dict[str, str]:
    claims = tokens.read(body.reset_token, tokens.PURPOSE_RESET)
    if not claims:
        raise HTTPException(400, "Your reset session expired. Please start again.")
    user = controller.get_users().find_one({"email": claims["sub"]})
    # The fingerprint changes once the password does, so a token works exactly once.
    if not user or tokens.password_fingerprint(user["password_hash"]) != claims.get("pwf"):
        raise HTTPException(400, "Your reset session expired. Please start again.")
    # The write is conditional on the hash we just checked, so two concurrent redemptions can't both win.
    ok, msg = controller.reset_password(claims["sub"], body.new_password, expected_hash=user["password_hash"])
    if not ok:
        raise HTTPException(400, msg)
    return {"status": "password_reset"}
