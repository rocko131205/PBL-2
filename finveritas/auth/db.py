"""MongoDB connection singleton for FinVeritas.

Reads connection settings from environment variables (via .env file).
Easily switchable from local MongoDB to MongoDB Atlas by changing MONGO_URI.
"""
from __future__ import annotations

import os
from datetime import datetime

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


def get_users() -> Collection:
    return get_db()["users"]


def get_file_history() -> Collection:
    return get_db()["file_history"]


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
        "created_at": datetime.utcnow(),
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
        "timestamp": datetime.utcnow(),
    }
