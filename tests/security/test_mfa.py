"""TOTP two-factor authentication."""
from __future__ import annotations

import time

import pyotp

from finveritas.auth import controller
from finveritas.security import config, mfa

from .conftest import STRONG_PASSWORD


def _enable(user) -> str:
    uid = str(user["_id"])
    secret, uri = controller.begin_mfa_enrolment(uid)
    assert uri.startswith("otpauth://totp/") and "FinVeritas" in uri
    # use the previous step so the first login can use the current one
    code = pyotp.TOTP(secret).at(time.time() - 30)
    ok, msg = controller.confirm_mfa_enrolment(uid, secret, code)
    assert ok, msg
    return secret


def test_enrolment_requires_a_valid_code(user):
    uid = str(user["_id"])
    secret, _ = controller.begin_mfa_enrolment(uid)
    ok, _ = controller.confirm_mfa_enrolment(uid, secret, "000000")
    assert not ok


def test_secret_is_encrypted_at_rest(user, mongo):
    secret = _enable(user)
    doc = mongo.users.find_one({"_id": user["_id"]})
    assert doc["mfa_enabled"] and secret not in str(doc)
    assert mfa.decrypt_secret(doc["mfa_secret_enc"]) == secret


def test_password_alone_is_not_enough_when_mfa_enabled(user):
    _enable(user)
    ok, result = controller.login_user("alice@example.com", STRONG_PASSWORD)
    assert ok and isinstance(result, dict) and result["mfa_required"]


def test_valid_code_completes_login(user):
    secret = _enable(user)
    _, pending = controller.login_user("alice@example.com", STRONG_PASSWORD)
    ok, token = controller.complete_mfa_login(pending["user_id"], pyotp.TOTP(secret).now())
    assert ok and controller.decode_token(token)


def test_code_cannot_be_replayed(user):
    secret = _enable(user)
    code = pyotp.TOTP(secret).now()
    uid = str(user["_id"])
    assert controller.complete_mfa_login(uid, code)[0]
    assert not controller.complete_mfa_login(uid, code)[0]


def test_mfa_guessing_is_rate_limited(user):
    secret = _enable(user)
    uid = str(user["_id"])
    for _ in range(config.MFA_MAX_FAILURES):
        controller.complete_mfa_login(uid, "000000")
    ok, msg = controller.complete_mfa_login(uid, pyotp.TOTP(secret).now())
    assert not ok and "Too many" in msg


def test_disabling_mfa_requires_a_current_code(user, mongo):
    secret = _enable(user)
    uid = str(user["_id"])
    assert not controller.disable_mfa(uid, "000000")[0]
    assert controller.disable_mfa(uid, pyotp.TOTP(secret).now())[0]
    assert not mongo.users.find_one({"_id": user["_id"]})["mfa_enabled"]


def test_tampered_ciphertext_is_rejected():
    enc = mfa.encrypt_secret(mfa.new_secret())
    assert mfa.decrypt_secret(enc[:-4] + "AAAA") is None
