"""Shared fixtures: an in-memory MongoDB (mongomock) and a strong test JWT secret."""
from __future__ import annotations

import mongomock
import pytest

from finveritas.auth import controller, db

STRONG_PASSWORD = "Str0ng!Passw0rd"


@pytest.fixture(autouse=True)
def secure_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "t" * 64)
    monkeypatch.delenv("FIELD_ENCRYPTION_KEY", raising=False)


@pytest.fixture(autouse=True)
def mongo():
    database = mongomock.MongoClient()["finveritas_test"]
    db._reset_for_tests(database)
    yield database
    db._reset_for_tests(mongomock.MongoClient()["finveritas_test_teardown"])


@pytest.fixture
def user(mongo):
    ok, msg = controller.register_user("Alice Analyst", "alice@example.com", "+919876543210",
                                       "Maharashtra", "Pune", STRONG_PASSWORD)
    assert ok, msg
    return mongo.users.find_one({"email": "alice@example.com"})


@pytest.fixture
def outbox(monkeypatch):
    """Capture OTP emails instead of sending them."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(controller, "_SMTP_USER", "noreply@example.com")
    monkeypatch.setattr(controller, "_SMTP_PASS", "app-password")
    monkeypatch.setattr(controller, "_deliver_async", lambda email, otp: sent.append((email, otp)))
    return sent
