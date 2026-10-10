"""Auth API: cookie flags, CSRF, revocation, inactivity, MFA, password reset, startup check."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from finveritas.auth import controller
from finveritas.security import mfa

from .conftest import STRONG_PASSWORD, csrf, login

REGISTER = {
    "full_name": "Bob Builder", "email": "bob@example.com", "country_code": "+91",
    "phone": "9876543210", "state": "Maharashtra", "city": "Pune", "password": STRONG_PASSWORD,
}


def test_health_is_public(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_register_then_login(client):
    assert client.post("/api/auth/register", json=REGISTER).status_code == 201
    r = login(client, "bob@example.com")
    assert r.json()["user"]["full_name"] == "Bob Builder"
    assert client.get("/api/auth/me").json()["email"] == "bob@example.com"


@pytest.mark.parametrize("field,value", [
    ("full_name", "B0b!"), ("email", "not-an-email"), ("phone", "123"),
    ("state", "Atlantis"), ("city", "Gotham"), ("password", "weak"),
])
def test_register_rejects_bad_input_server_side(client, field, value):
    r = client.post("/api/auth/register", json={**REGISTER, field: value})
    assert r.status_code in (400, 422)


def test_duplicate_registration_conflicts(client, user):
    r = client.post("/api/auth/register", json={**REGISTER, "email": "alice@example.com"})
    assert r.status_code == 409


def test_session_cookie_is_httponly_and_strict(client, user):
    r = login(client)
    cookie = next(h for h in r.headers.get_list("set-cookie") if h.startswith("fv_session="))
    assert "httponly" in cookie.lower() and "samesite=strict" in cookie.lower()
    assert "token" not in r.text  # the JWT never appears in the body


def test_login_failure_is_generic_and_unauthenticated_me_is_401(client, user):
    r = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "Wrong!Passw0rd"})
    assert r.status_code == 401 and r.json()["detail"] == controller.GENERIC_LOGIN_ERROR
    assert client.get("/api/auth/me").status_code == 401


def test_logout_revokes_session_and_requires_csrf_on_writes(client, user):
    login(client)
    token = client.cookies.get("fv_session")
    assert client.post("/api/auth/logout").status_code == 200  # logout is exempt so stale tabs can clear
    assert controller.decode_token(token) is None
    assert client.get("/api/auth/me").status_code == 401


def test_revoked_token_is_rejected(client, user):
    login(client)
    controller.logout(client.cookies.get("fv_session"))
    assert client.get("/api/auth/me").status_code == 401


def test_inactivity_timeout_ends_the_session(client, user, mongo):
    login(client)
    assert client.get("/api/auth/me").status_code == 200
    mongo.sessions.update_many({}, {"$set": {"last_seen": datetime.now(timezone.utc) - timedelta(minutes=16)}})
    assert client.get("/api/auth/me").status_code == 401
    assert mongo.sessions.count_documents({"revoked": True}) == 1


def test_tampered_cookie_is_rejected(client, user):
    login(client)
    client.cookies.set("fv_session", client.cookies.get("fv_session") + "x")
    assert client.get("/api/auth/me").status_code == 401


def test_mfa_login_flow(client, user, mongo):
    import pyotp
    secret = mfa.new_secret()
    code = pyotp.TOTP(secret).now()
    assert controller.confirm_mfa_enrolment(str(user["_id"]), secret, code)[0]

    r = client.post("/api/auth/login", json={"email": "alice@example.com", "password": STRONG_PASSWORD})
    assert r.json()["mfa_required"] is True and "fv_session" not in client.cookies
    bad = client.post("/api/auth/login/mfa", json={"mfa_token": r.json()["mfa_token"], "code": "000000"})
    assert bad.status_code == 401
    # a garbage token can't stand in for an MFA token
    assert client.post("/api/auth/login/mfa", json={"mfa_token": "garbage", "code": code}).status_code == 401


def test_password_reset_flow_is_single_use(client, user, outbox):
    assert client.post("/api/password-reset/send-otp", json={"email": "alice@example.com"}).status_code == 200
    code = outbox[-1][1]
    wrong = f"{(int(code) + 1) % 10**6:06d}"
    assert client.post("/api/password-reset/verify-otp", json={"email": "alice@example.com", "code": wrong}).status_code == 400
    r = client.post("/api/password-reset/verify-otp", json={"email": "alice@example.com", "code": code})
    token = r.json()["reset_token"]

    assert client.post("/api/password-reset/reset", json={"reset_token": token, "new_password": "weak"}).status_code == 400
    assert client.post("/api/password-reset/reset", json={"reset_token": token, "new_password": "N3w!Passw0rd#"}).status_code == 200
    # replaying the same token fails: the password changed, so its fingerprint no longer matches
    assert client.post("/api/password-reset/reset", json={"reset_token": token, "new_password": "An0ther!Passw0rd"}).status_code == 400
    assert controller.login_user("alice@example.com", "N3w!Passw0rd#")[0]


def test_reset_rejects_forged_and_wrong_purpose_tokens(client, user):
    from api import tokens
    mfa_token = tokens.issue(tokens.PURPOSE_MFA, "alice@example.com", 5)
    r = client.post("/api/password-reset/reset", json={"reset_token": mfa_token, "new_password": "N3w!Passw0rd#"})
    assert r.status_code == 400


def test_otp_attempts_are_capped_through_the_api(client, user, outbox):
    from finveritas.security import config
    client.post("/api/password-reset/send-otp", json={"email": "alice@example.com"})
    code = outbox[-1][1]
    wrong = f"{(int(code) + 1) % 10**6:06d}"
    for _ in range(config.OTP_MAX_ATTEMPTS):
        client.post("/api/password-reset/verify-otp", json={"email": "alice@example.com", "code": wrong})
    r = client.post("/api/password-reset/verify-otp", json={"email": "alice@example.com", "code": code})
    assert r.status_code == 400


def test_send_otp_reveals_nothing_about_account_existence(client, user, outbox):
    a = client.post("/api/password-reset/send-otp", json={"email": "alice@example.com"})
    b = client.post("/api/password-reset/send-otp", json={"email": "nobody@example.com"})
    assert a.status_code == b.status_code and a.json() == b.json()


def test_app_refuses_to_start_with_weak_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "finveritas-change-this-secret")
    with pytest.raises(RuntimeError, match="security configuration"):
        with TestClient(app):
            pass


def test_geo_endpoints(client):
    assert "Maharashtra" in client.get("/api/geo/states").json()
    assert "Pune" in client.get("/api/geo/cities", params={"state": "Maharashtra"}).json()
