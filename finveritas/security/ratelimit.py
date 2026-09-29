"""Sliding-window attempt counter backed by MongoDB (`rate_limits` collection).

Each attempt is stored as its own document with a TTL index, so counts survive
app restarts and are shared by every server process — unlike Streamlit
session_state, which an attacker resets simply by opening a new tab.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def record(key: str, window_minutes: int) -> None:
    """Record one attempt against `key` (e.g. 'login:alice@example.com')."""
    from finveritas.auth.db import get_rate_limits

    now = _now()
    get_rate_limits().insert_one({
        "key": key,
        "ts": now,
        "expires_at": now + timedelta(minutes=window_minutes),
    })


def count(key: str, window_minutes: int) -> int:
    from finveritas.auth.db import get_rate_limits

    since = _now() - timedelta(minutes=window_minutes)
    return get_rate_limits().count_documents({"key": key, "ts": {"$gte": since}})


def is_limited(key: str, limit: int, window_minutes: int) -> bool:
    return count(key, window_minutes) >= limit


def retry_after_minutes(key: str, window_minutes: int) -> int:
    """Minutes until the oldest attempt in the window ages out (>= 1)."""
    from finveritas.auth.db import get_rate_limits

    since = _now() - timedelta(minutes=window_minutes)
    oldest = get_rate_limits().find_one({"key": key, "ts": {"$gte": since}}, sort=[("ts", 1)])
    if not oldest:
        return 0
    ts = oldest["ts"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    remaining = (ts + timedelta(minutes=window_minutes)) - _now()
    return max(1, int(remaining.total_seconds() // 60) + 1)


def clear(key: str) -> None:
    from finveritas.auth.db import get_rate_limits

    get_rate_limits().delete_many({"key": key})
