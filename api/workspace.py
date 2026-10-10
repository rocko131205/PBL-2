"""Per-user workspace: the dataset a user has loaded plus their upload-page preferences.

This replaces `st.session_state` ("ocr_cache", "active_source", "reported_scale", ...).
Every query is filtered by the authenticated user's id, so one user can never read
another's data.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from api import views
from finveritas.auth.db import get_workspaces
from finveritas.ingestion.scale import rescale_payload


def clean(obj: Any) -> Any:
    """Make provider output safe for MongoDB and JSON: no NaN/inf, numpy scalars or odd keys."""
    if isinstance(obj, Enum):
        return clean(obj.value)
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [clean(v) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, (str, int)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if hasattr(obj, "item"):  # numpy scalar
        try:
            return clean(obj.item())
        except Exception:
            return None
    return str(obj)


def load(user_id: str) -> dict[str, Any] | None:
    return get_workspaces().find_one({"user_id": user_id})


def replace(user_id: str, *, source: str, source_label: str, payload: dict[str, Any],
            ticker: str | None = None) -> dict[str, Any]:
    """Start a fresh workspace from newly loaded data (drops the previous dataset and results)."""
    doc = {
        "user_id": user_id,
        "source": source,                 # "pdf" | "ticker" | "csv"
        "source_label": source_label,
        "ticker": ticker,
        "payload": clean(payload),
        "scale": 1.0,
        "updated_at": datetime.now(timezone.utc),
    }
    get_workspaces().replace_one({"user_id": user_id}, doc, upsert=True)
    return doc


def update(user_id: str, set_fields: dict[str, Any] | None = None, unset: list[str] | None = None) -> None:
    op: dict[str, Any] = {"$set": {**(set_fields or {}), "updated_at": datetime.now(timezone.utc)}}
    if unset:
        op["$unset"] = {k: "" for k in unset}
    get_workspaces().update_one({"user_id": user_id}, op)


def clear(user_id: str) -> None:
    get_workspaces().delete_one({"user_id": user_id})


def display_payload(doc: dict[str, Any]) -> dict[str, Any]:
    """The payload as the user should see it: reporting scale applied (tickers are already absolute)."""
    payload = doc["payload"]
    if doc["source"] == "ticker" or doc.get("scale", 1.0) == 1.0:
        return payload
    return rescale_payload(payload, doc["scale"])


def view(doc: dict[str, Any] | None, *, fmp_configured: bool, av_configured: bool) -> dict[str, Any]:
    """Everything the Upload page needs, except the (slower, cached) credibility report."""
    if not doc:
        return {"loaded": False}
    payload = doc["payload"]
    shown = display_payload(doc)
    entity = payload.get("entity") or {}
    is_ticker = doc["source"] == "ticker"
    return {
        "loaded": True,
        "source": doc["source"],
        "source_label": doc["source_label"],
        "ticker": doc.get("ticker"),
        "entity": {"name": str(entity.get("entity_id") or "—"), "currency": entity.get("currency")},
        "fields_loaded": sorted(views.available_fields(payload)),
        "scale": {
            "applicable": not is_ticker,
            "multiplier": 1.0 if is_ticker else doc.get("scale", 1.0),
            "options": views.SCALE_OPTIONS,
        },
        "cards": views.metric_cards(shown),
        "preview": views.preview_rows(payload),
        "readiness": views.readiness(payload),
        "periods": views.periods_in(payload),
        "qualitative": entity.get("qualitative_context") or "",
        "supplement": {"ticker": doc.get("ticker"), "fmp": is_ticker and fmp_configured, "alphavantage": is_ticker and av_configured},
        "credibility": doc.get("credibility"),
    }
