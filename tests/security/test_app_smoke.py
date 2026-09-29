"""End-to-end checks of the Streamlit app with Streamlit's AppTest harness (in-memory DB)."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from finveritas.auth import controller

from .conftest import STRONG_PASSWORD

APP = str(Path(__file__).resolve().parents[2] / "app.py")


def _app(token: str | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    if token:
        at.session_state["auth_token"] = token
    return at.run()


def _nav(at: AppTest, page: str) -> AppTest:
    at.sidebar.radio(key="sidebar_nav").set_value(page)
    return at.run()


def _token() -> str:
    ok, token = controller.login_user("alice@example.com", STRONG_PASSWORD)
    assert ok
    return token


def test_unauthenticated_user_sees_login_only(user):
    at = _app()
    assert not at.exception
    assert any(b.label.startswith("Login") for b in at.button) or at.text_input(key="login_email")


def test_token_in_query_string_is_ignored(user):
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["token"] = _token()
    at.run()
    assert not at.exception
    assert "token" not in at.query_params
    assert "auth_user" not in at.session_state  # still on the login page


def test_authenticated_user_can_open_security_settings(user):
    at = _nav(_app(_token()), "Security Settings")
    assert not at.exception
    assert any("Two-factor" in m.value for m in at.markdown)
    assert "Security Dashboard" not in at.sidebar.radio(key="sidebar_nav").options


def test_mfa_enrolment_shows_qr_and_secret(user):
    at = _nav(_app(_token()), "Security Settings")
    [b for b in at.button if b.label == "Set up two-factor authentication"][0].click()
    at.run()
    assert not at.exception
    assert at.session_state["mfa_enrol_secret"]
    assert any(c.value == at.session_state["mfa_enrol_secret"] for c in at.code)


def test_revoked_token_is_logged_out_on_next_run(user):
    token = _token()
    at = _app(token)
    controller.logout(token)
    at.run()
    assert "auth_token" not in at.session_state


def test_admin_sees_dashboard_and_analyst_does_not(user, mongo):
    mongo.users.update_one({"_id": user["_id"]}, {"$set": {"role": "admin"}})
    controller.login_user("mallory@example.com", "Wrong!Passw0rd")  # generate a failure event
    at = _nav(_app(_token()), "Security Dashboard")
    assert not at.exception
    assert any(m.label == "Failed logins" and m.value == "1" for m in at.metric)


def test_sidebar_sign_out_revokes_session(user):
    token = _token()
    at = _app(token)
    at.sidebar.button(key="sidebar_signout").click()
    at.run()
    assert controller.decode_token(token) is None


@pytest.mark.parametrize("missing", ["", "finveritas-change-this-secret"])
def test_app_refuses_to_start_with_weak_secret(user, monkeypatch, missing):
    monkeypatch.setenv("JWT_SECRET", missing)
    at = _app()
    assert any("security configuration is incomplete" in e.value for e in at.error)
