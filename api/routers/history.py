"""My File History: one row per completed analysis, newest first."""
from __future__ import annotations

from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends

from api.deps import current_user
from finveritas.auth.db import get_file_history

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/history")
def history(user: dict = Depends(current_user)) -> list[dict[str, Any]]:
    rows = get_file_history().find({"user_id": ObjectId(user["user_id"])}).sort("timestamp", -1).limit(100)
    return [{
        "id": str(r["_id"]),
        "analysis_id": r.get("analysis_id"),
        "entity_name": r.get("entity_name"),
        "source_type": r.get("source_type"),
        "source_label": r.get("source_label"),
        "credibility_score": r.get("credibility_score"),
        "fields_loaded": r.get("fields_loaded") or [],
        "timestamp": r.get("timestamp"),
    } for r in rows]
