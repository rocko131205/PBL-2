"""API test fixtures: reuse the in-memory MongoDB / secret / user fixtures and add a client."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.security.conftest import STRONG_PASSWORD, mongo, outbox, secure_env, user  # noqa: F401

from api.main import app


@pytest.fixture(autouse=True)
def plain_http_cookies(monkeypatch):
    # TestClient talks plain http, so Secure cookies would never be sent back.
    monkeypatch.setenv("COOKIE_SECURE", "false")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def login(client: TestClient, email="alice@example.com", password=STRONG_PASSWORD):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("fv_csrf")}
