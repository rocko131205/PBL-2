"""Regression tests for authentication findings (see docs/security/PENTEST_REPORT.md)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from finveritas.auth import controller
from finveritas.security import audit, config, sessions

from .conftest import STRONG_PASSWORD


# ── FV-06: fail-closed secret ─────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["", "short", "finveritas-change-this-secret", "your_secret"])
def test_weak_or_missing_jwt_secret_is_refused(monkeypatch, value):
    monkeypatch.setenv("JWT_SECRET", value)
    with pytest.raises(config.SecurityConfigError):
        config.jwt_secret()
    assert config.validate_startup()


# ── FV-04: user enumeration ───────────────────────────────────────────────────

def test_login_error_is_identical_for_unknown_email_and_wrong_password(user):
    _, unknown = controller.login_user("nobody@example.com", "whatever")
    _, wrong = controller.login_user("alice@example.com", "Wrong!Passw0rd")
    assert unknown == wrong == controller.GENERIC_LOGIN_ERROR


def test_password_reset_response_is_identical_for_unknown_email(user, outbox):
    state_a, state_b = {}, {}
    ok_a, msg_a = controller.send_otp("alice@example.com", state_a)
    ok_b, msg_b = controller.send_otp("nobody@example.com", state_b)
    assert (ok_a, msg_a) == (ok_b, msg_b)
    assert [e for e, _ in outbox] == ["alice@example.com"]  # only real accounts get mail


# ── FV-05: brute force / credential stuffing ──────────────────────────────────

def test_account_locks_after_repeated_failures_even_with_correct_password(user, mongo):
    for _ in range(config.LOGIN_MAX_FAILURES):
        ok, _ = controller.login_user("alice@example.com", "Wrong!Passw0rd")
        assert not ok
    ok, msg = controller.login_user("alice@example.com", STRONG_PASSWORD)
    assert not ok and "Too many failed attempts" in msg
    assert mongo.audit_log.count_documents({"event": audit.LOGIN_LOCKED}) == 1


def test_lockout_is_not_bypassed_by_email_case_or_whitespace(user):
    for i in range(config.LOGIN_MAX_FAILURES):
        variant = [" ALICE@example.com", "Alice@Example.com ", "alice@EXAMPLE.COM"][i % 3]
        controller.login_user(variant, "Wrong!Passw0rd")
    ok, _ = controller.login_user("alice@example.com", STRONG_PASSWORD)
    assert not ok


def test_successful_login_clears_failure_counter(user):
    for _ in range(config.LOGIN_MAX_FAILURES - 1):
        controller.login_user("alice@example.com", "Wrong!Passw0rd")
    ok, _ = controller.login_user("alice@example.com", STRONG_PASSWORD)
    assert ok
    for _ in range(config.LOGIN_MAX_FAILURES - 1):
        controller.login_user("alice@example.com", "Wrong!Passw0rd")
    ok, _ = controller.login_user("alice@example.com", STRONG_PASSWORD)
    assert ok


def test_failed_and_successful_logins_are_audited(user, mongo):
    controller.login_user("alice@example.com", "Wrong!Passw0rd")
    controller.login_user("alice@example.com", STRONG_PASSWORD)
    events = [e["event"] for e in mongo.audit_log.find().sort("timestamp", 1)]
    assert audit.LOGIN_FAILURE in events and audit.LOGIN_SUCCESS in events
    # passwords must never be written to the log
    assert "Wrong!Passw0rd" not in str(list(mongo.audit_log.find()))


# ── FV-01 / FV-09: sessions ───────────────────────────────────────────────────

def _login(email="alice@example.com", pw=STRONG_PASSWORD) -> str:
    ok, token = controller.login_user(email, pw)
    assert ok and isinstance(token, str)
    return token


def test_valid_token_decodes_with_required_claims(user):
    payload = controller.decode_token(_login())
    assert payload and payload["email"] == "alice@example.com"
    assert {"jti", "iat", "exp", "iss", "sub"} <= payload.keys()


def test_logout_revokes_token_server_side(user):
    token = _login()
    controller.logout(token)
    assert controller.decode_token(token) is None


def test_password_reset_revokes_all_sessions(user):
    t1, t2 = _login(), _login()
    ok, _ = controller.reset_password("alice@example.com", "N3w!Passw0rd#")
    assert ok
    assert controller.decode_token(t1) is None and controller.decode_token(t2) is None


def test_sign_out_other_sessions_keeps_current(user):
    current, other = _login(), _login()
    jti = controller.decode_token(current)["jti"]
    sessions.revoke_all(str(user["_id"]), except_jti=jti)
    assert controller.decode_token(current) and controller.decode_token(other) is None


def test_forged_token_with_wrong_secret_is_rejected(user):
    payload = controller.decode_token(_login())
    forged = jwt.encode({**payload, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        "attacker-secret-" * 4, algorithm="HS256")
    assert controller.decode_token(forged) is None


def test_alg_none_token_is_rejected(user):
    payload = controller.decode_token(_login())
    unsigned = jwt.encode({**payload, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                          None, algorithm="none")
    assert controller.decode_token(unsigned) is None


@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
def test_token_signed_with_old_default_secret_is_rejected(user):
    """Before the fix, anyone could mint tokens with the public fallback secret."""
    now = datetime.now(timezone.utc)
    forged = jwt.encode({"user_id": str(user["_id"]), "email": user["email"], "full_name": "x",
                         "exp": now + timedelta(hours=1)},
                        "finveritas-change-this-secret", algorithm="HS256")
    assert controller.decode_token(forged) is None


def test_validly_signed_token_without_registered_session_is_rejected(user):
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": str(user["_id"]), "user_id": str(user["_id"]), "email": user["email"],
                        "full_name": "x", "jti": "never-issued", "iat": now,
                        "exp": now + timedelta(hours=1), "iss": config.JWT_ISSUER},
                       config.jwt_secret(), algorithm="HS256")
    assert controller.decode_token(token) is None


def test_expired_token_is_rejected(user, mongo):
    token = _login()
    payload = jwt.decode(token, config.jwt_secret(), algorithms=["HS256"], issuer=config.JWT_ISSUER)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode({**payload, "exp": past}, config.jwt_secret(), algorithm="HS256")
    assert controller.decode_token(expired) is None


# ── Password policy enforced server-side ──────────────────────────────────────

@pytest.mark.parametrize("pw", ["short1!", "alllowercase1!", "ALLUPPER1!", "NoDigits!!", "NoSpecial11", "Password@123"])
def test_register_rejects_weak_passwords_server_side(mongo, pw):
    ok, msg = controller.register_user("Bob", "bob@example.com", "1", "S", "C", pw)
    assert not ok and msg.startswith("Password needs")


def test_passwords_are_stored_as_bcrypt_hashes(user):
    assert user["password_hash"].startswith("$2") and STRONG_PASSWORD not in user["password_hash"]


def test_registration_hides_internal_errors(mongo, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("mongodb://admin:hunter2@db.internal:27017 timed out")
    monkeypatch.setattr(mongo.users, "insert_one", boom)
    monkeypatch.setattr("finveritas.auth.controller.get_users", lambda: mongo.users)
    ok, msg = controller.register_user("Bob", "bob@example.com", "1", "S", "C", STRONG_PASSWORD)
    assert not ok and "hunter2" not in msg and "db.internal" not in msg


# ── RBAC ──────────────────────────────────────────────────────────────────────

def test_new_users_are_not_admins_and_role_is_read_from_db(user, mongo):
    uid = str(user["_id"])
    assert user["role"] == "analyst" and not controller.is_admin(uid)
    mongo.users.update_one({"_id": user["_id"]}, {"$set": {"role": "admin"}})
    assert controller.is_admin(uid)
    mongo.users.update_one({"_id": user["_id"]}, {"$set": {"role": "analyst"}})
    assert not controller.is_admin(uid)  # demotion applies immediately


def test_login_results_are_counted_in_metrics(user):
    from prometheus_client import REGISTRY

    def count(result):
        return REGISTRY.get_sample_value("finveritas_logins_total", {"result": result}) or 0.0

    ok, fail = count("success"), count("failure")
    assert controller.login_user("alice@example.com", "Wrong!Passw0rd")[0] is False
    assert controller.login_user("alice@example.com", STRONG_PASSWORD)[0] is True
    assert (count("failure"), count("success")) == (fail + 1, ok + 1)
