"""Password-reset OTP hardening (FV-02, FV-03, FV-07)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from finveritas.auth import controller
from finveritas.security import config

from .conftest import STRONG_PASSWORD


def _request(outbox, state=None, email="alice@example.com"):
    state = {} if state is None else state
    ok, _ = controller.send_otp(email, state)
    assert ok
    return state, outbox[-1][1]


def _wrong(code: str) -> str:
    return f"{(int(code) + 1) % 10**6:06d}"


def test_otp_uses_csprng_and_has_full_length():
    codes = {controller._generate_otp() for _ in range(300)}
    assert all(len(c) == 6 and c.isdigit() for c in codes)
    assert len(codes) > 290  # no obvious repetition


def test_otp_generation_does_not_use_random_module(monkeypatch):
    import random
    monkeypatch.setattr(random, "choices", lambda *a, **k: (_ for _ in ()).throw(AssertionError("random used")))
    controller._generate_otp()


def test_otp_is_stored_hashed_not_plaintext(user, outbox, mongo):
    _, code = _request(outbox)
    doc = mongo.password_resets.find_one({"email": "alice@example.com"})
    assert code not in str(doc) and len(doc["otp_hash"]) == 64


def test_correct_otp_then_reset_works_and_old_password_stops_working(user, outbox):
    state, code = _request(outbox)
    ok, _ = controller.verify_otp(code, state)
    assert ok
    ok, _ = controller.complete_password_reset(state, "N3w!Passw0rd#")
    assert ok
    assert not controller.login_user("alice@example.com", STRONG_PASSWORD)[0]
    assert controller.login_user("alice@example.com", "N3w!Passw0rd#")[0]


def test_otp_brute_force_is_capped(user, outbox):
    """The original bug: unlimited guesses let an attacker walk all 10^6 codes."""
    state, code = _request(outbox)
    for _ in range(config.OTP_MAX_ATTEMPTS):
        ok, _ = controller.verify_otp(_wrong(code), state)
        assert not ok
    ok, _ = controller.verify_otp(code, state)  # correct code, but too late — it was burned
    assert not ok


def test_otp_attempt_cap_survives_a_new_browser_session(user, outbox):
    """Attempts are counted in the database, so opening a fresh tab doesn't reset them."""
    _, code = _request(outbox)
    for _ in range(config.OTP_MAX_ATTEMPTS):
        controller.verify_otp(_wrong(code), {"otp_email": "alice@example.com"})
    ok, _ = controller.verify_otp(code, {"otp_email": "alice@example.com"})
    assert not ok


def test_otp_is_single_use(user, outbox):
    state, code = _request(outbox)
    assert controller.verify_otp(code, state)[0]
    assert not controller.verify_otp(code, {"otp_email": "alice@example.com"})[0]


def test_expired_otp_is_rejected(user, outbox, mongo):
    state, code = _request(outbox)
    mongo.password_resets.update_one({"email": "alice@example.com"},
                                     {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert not controller.verify_otp(code, state)[0]


def test_new_code_invalidates_the_previous_one(user, outbox):
    state, first = _request(outbox)
    _, second = _request(outbox, state)
    if first != second:
        assert not controller.verify_otp(first, dict(state))[0]
    assert controller.verify_otp(second, state)[0]


def test_otp_requests_are_rate_limited_per_email(user, outbox):
    for _ in range(config.OTP_MAX_SENDS):
        assert controller.send_otp("alice@example.com", {})[0]
    ok, msg = controller.send_otp("alice@example.com", {})
    assert not ok and "Too many" in msg


def test_reset_cannot_be_completed_without_verified_otp(user):
    ok, _ = controller.complete_password_reset({}, "N3w!Passw0rd#")
    assert not ok
    forged = {"reset_grant": {"email": "alice@example.com",
                              "expires": datetime.now(timezone.utc) - timedelta(seconds=1)}}
    assert not controller.complete_password_reset(forged, "N3w!Passw0rd#")[0]


def test_reset_enforces_password_policy(user, outbox):
    state, code = _request(outbox)
    controller.verify_otp(code, state)
    ok, msg = controller.complete_password_reset(state, "weak")
    assert not ok and msg.startswith("Password needs")


def test_unconfigured_smtp_reports_config_error_without_leaking_account_existence(user, monkeypatch):
    monkeypatch.setattr(controller, "_SMTP_USER", "")
    a = controller.send_otp("alice@example.com", {})
    b = controller.send_otp("nobody@example.com", {})
    assert a == b and not a[0]


def test_smtp_never_disables_certificate_verification():
    import inspect
    src = inspect.getsource(controller._send_otp_email)
    assert "CERT_NONE" not in src and "check_hostname = False" not in src
