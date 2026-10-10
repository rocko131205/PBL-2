"""MongoDB connection singleton for FinVeritas.

Reads connection settings from environment variables (via .env file).
Easily switchable from local MongoDB to MongoDB Atlas by changing MONGO_URI.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

load_dotenv()

_client: MongoClient | None = None
_db: Database | None = None


def get_db() -> Database:
    """Return the MongoDB database instance (singleton)."""
    global _client, _db
    if _db is None:
        uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        _db = _client[os.getenv("MONGO_DB_NAME", "finveritas")]
        _ensure_indexes(_db)
    return _db


def _ensure_indexes(db: Database) -> None:
    """Create required indexes if they don't already exist."""
    # users.email must be unique
    db.users.create_index([("email", ASCENDING)], unique=True, background=True)
    # file_history queries are always filtered by user_id
    db.file_history.create_index([("user_id", ASCENDING)], background=True)
    db.file_history.create_index([("user_id", ASCENDING), ("timestamp", ASCENDING)], background=True)

    # Security collections — TTL indexes make MongoDB purge expired records itself
    db.sessions.create_index([("jti", ASCENDING)], unique=True)
    db.sessions.create_index([("user_id", ASCENDING)])
    db.sessions.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    db.rate_limits.create_index([("key", ASCENDING), ("ts", ASCENDING)])
    db.rate_limits.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    db.password_resets.create_index([("email", ASCENDING)], unique=True)
    db.password_resets.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    db.audit_log.create_index([("timestamp", ASCENDING)])
    db.audit_log.create_index([("user_id", ASCENDING), ("timestamp", ASCENDING)])
    db.audit_log.create_index([("event", ASCENDING), ("timestamp", ASCENDING)])

    # One workspace (loaded dataset + preferences) per user — replaces st.session_state for the API.
    db.workspaces.create_index([("user_id", ASCENDING)], unique=True)
    # Analysis runs (background jobs + their results), always queried per user.
    db.analyses.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)])


def get_users() -> Collection:
    return get_db()["users"]


def get_file_history() -> Collection:
    return get_db()["file_history"]


def get_sessions() -> Collection:
    return get_db()["sessions"]


def get_rate_limits() -> Collection:
    return get_db()["rate_limits"]


def get_password_resets() -> Collection:
    return get_db()["password_resets"]


def get_audit_log() -> Collection:
    return get_db()["audit_log"]


def get_workspaces() -> Collection:
    return get_db()["workspaces"]


def get_analyses() -> Collection:
    return get_db()["analyses"]


def get_analysis_locks() -> Collection:
    """One document per user whose _id is the user id: holding it means "an analysis is running"."""
    return get_db()["analysis_locks"]


def _reset_for_tests(db: Database) -> None:
    """Point the singleton at an injected database (used by the test suite)."""
    global _client, _db
    _client, _db = None, db
    _ensure_indexes(db)


# ---------------------------------------------------------------------------
# Document schemas (as plain dicts — for reference and validation helpers)
# ---------------------------------------------------------------------------

def make_user_doc(
    full_name: str,
    email: str,
    phone: str,
    state: str,
    city: str,
    password_hash: str,
) -> dict:
    """Create a new user document (ready to insert into users collection)."""
    return {
        "full_name": full_name,
        "email": email.lower().strip(),
        "phone": phone.strip(),
        "state": state,
        "city": city,
        "password_hash": password_hash,
        "role": "analyst",          # "analyst" | "admin" — promote admins in the DB, never via the UI
        "mfa_enabled": False,
        "mfa_secret_enc": None,     # Fernet-encrypted TOTP secret
        "mfa_last_step": None,      # last accepted TOTP time-step (replay protection)
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
    }


def make_history_doc(
    user_id: str,
    source_type: str,
    source_label: str,
    entity_name: str,
    fields_loaded: list[str],
    credibility_score: int,
) -> dict:
    """Create a file history document (ready to insert into file_history collection)."""
    from bson import ObjectId
    return {
        "user_id": ObjectId(user_id),
        "source_type": source_type,       # "pdf" | "ticker" | "csv"
        "source_label": source_label,     # e.g. "yfinance · AAPL"
        "entity_name": entity_name,
        "fields_loaded": fields_loaded,
        "credibility_score": credibility_score,
        "timestamp": datetime.now(timezone.utc),
    }
