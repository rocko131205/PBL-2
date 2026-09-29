"""Server-side password policy.

The UI already checks these rules, but UI checks can be bypassed, so the
controller enforces the same policy before hashing anything.
"""
from __future__ import annotations

import re

MIN_LENGTH = 8
MAX_LENGTH = 72  # bcrypt silently truncates beyond 72 bytes

_COMMON = {
    "password", "password1", "password123", "passw0rd", "qwerty123", "12345678",
    "123456789", "iloveyou", "admin123", "welcome1", "letmein1", "Password@123",
    "Password1!", "Qwerty@123", "Admin@123", "Welcome@123",
}


def password_issues(password: str) -> list[str]:
    """Return human-readable policy violations (empty list = acceptable)."""
    issues: list[str] = []
    if len(password) < MIN_LENGTH:
        issues.append(f"at least {MIN_LENGTH} chars")
    if len(password.encode()) > MAX_LENGTH:
        issues.append(f"at most {MAX_LENGTH} bytes")
    if not re.search(r"[A-Z]", password):
        issues.append("uppercase")
    if not re.search(r"[a-z]", password):
        issues.append("lowercase")
    if not re.search(r"\d", password):
        issues.append("number")
    if not re.search(r"[^A-Za-z0-9]", password):
        issues.append("special char")
    if password in _COMMON or password.lower() in {c.lower() for c in _COMMON}:
        issues.append("not a commonly used password")
    return issues
