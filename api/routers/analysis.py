"""Run the analysis pipeline and serve its results (Financial Analysis / Agent Workflow pages)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from api import jobs, report, workspace
from api.deps import current_user
from finveritas.analysis.assistant import answer_question, explain_results
from finveritas.analysis.metrics.debt_service import LoanTerms, compute_dscr_schedule
from finveritas.analysis.metrics.memo import build_memo, render_memo_html
from finveritas.auth.db import get_analyses
from finveritas.security import ratelimit

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

AI_MAX = 20                  # assistant calls per user per window (each one hits the LLM)
AI_WINDOW_MINUTES = 10
QA_KEEP = 20

# Opened in a new tab for printing: even if the memo contained hostile markup it can't run script.
MEMO_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}


def _summary(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "status": doc["status"],
        "stages": doc.get("stages") or [],
        "entity": doc.get("entity"),
        "source_label": doc.get("source_label"),
        "created_at": doc.get("created_at"),
        "finished_at": doc.get("finished_at"),
        "error": doc.get("error"),
    }


def _load(analysis_id: str, user_id: str) -> dict[str, Any]:
    """A run the caller owns. Someone else's id looks exactly like a missing one."""
    try:
        oid = ObjectId(analysis_id)
    except (InvalidId, TypeError):
        raise HTTPException(404, "Analysis not found.") from None
    doc = get_analyses().find_one({"_id": oid, "user_id": user_id})
    if not doc:
        raise HTTPException(404, "Analysis not found.")
    return jobs.reap(doc)  # a run whose process died is reported as failed, never "running" forever


def _done(analysis_id: str, user_id: str) -> dict[str, Any]:
    doc = _load(analysis_id, user_id)
    if doc["status"] != "done":
        raise HTTPException(409, "This analysis hasn't finished yet.")
    return doc


def _ai_throttle(user_id: str) -> None:
    key = f"assistant:{user_id}"
    if ratelimit.is_limited(key, AI_MAX, AI_WINDOW_MINUTES):
        raise HTTPException(429, "You're asking the assistant too quickly. Please wait a few minutes.")
    ratelimit.record(key, AI_WINDOW_MINUTES)


# ── Running ──────────────────────────────────────────────────────────────────

@router.post("", status_code=202)
def start(user: dict = Depends(current_user)) -> dict[str, Any]:
    uid = user["user_id"]
    ws = workspace.load(uid)
    if not ws:
        raise HTTPException(400, "Load a statement on the Upload page first.")
    if jobs.throttled(uid):
        raise HTTPException(429, "You've started several analyses recently. Please wait a few minutes.")
    try:
        analysis_id = jobs.start(uid, ws)  # atomic: concurrent starts can't both succeed
    except jobs.AlreadyRunning as running:
        raise HTTPException(409, detail={"detail": "An analysis is already running.", "id": running.analysis_id}) from None
    return _summary(_load(analysis_id, uid))


@router.get("/current")
def current(user: dict = Depends(current_user)) -> dict[str, Any]:
    """The run linked to the currently loaded data, if any."""
    ws = workspace.load(user["user_id"])
    if not ws or not ws.get("analysis_id"):
        return {"status": "none", "has_data": bool(ws)}
    try:
        return {**_summary(_load(ws["analysis_id"], user["user_id"])), "has_data": True}
    except HTTPException:
        return {"status": "none", "has_data": True}


@router.get("/{analysis_id}")
def get(analysis_id: str, user: dict = Depends(current_user)) -> dict[str, Any]:
    doc = _load(analysis_id, user["user_id"])
    out = _summary(doc)
    if doc["status"] == "done":
        out["report"] = report.build(doc)
    return out


@router.get("/{analysis_id}/raw")
def raw(analysis_id: str, user: dict = Depends(current_user)) -> dict[str, Any]:
    return report.raw_state(_done(analysis_id, user["user_id"]))


# ── Debt serviceability ──────────────────────────────────────────────────────

class DscrIn(BaseModel):
    principal: float = Field(gt=0, le=1e16)
    annual_rate_pct: float = Field(ge=0, le=100)
    tenure_years: int = Field(ge=1, le=40)
    structure: Literal["equal_installment", "bullet", "balloon"] = "equal_installment"
    moratorium_years: int = Field(0, ge=0, le=10)
    existing_annual_debt_service: float = Field(0, ge=0, le=1e16)
    basis: Literal["cfads", "ocf", "ebitda", "ebit"] = "cfads"


@router.post("/{analysis_id}/dscr")
def dscr(analysis_id: str, body: DscrIn, user: dict = Depends(current_user)) -> dict[str, Any]:
    doc = _done(analysis_id, user["user_id"])
    record = report.record_of(doc["result"])
    if record is None:
        raise HTTPException(400, "This analysis has no financial record to assess.")
    if body.basis not in {b["key"] for b in report.available_bases(record)}:
        raise HTTPException(422, "That cash basis isn't available for this company's data.")
    if body.moratorium_years >= body.tenure_years:
        raise HTTPException(422, "The moratorium must be shorter than the loan tenure.")

    terms = LoanTerms(**body.model_dump(exclude={"basis"}))
    result = compute_dscr_schedule(record, terms, basis=body.basis)
    view = report.dscr_view(result, record.currency, body.existing_annual_debt_service,
                            body.structure, body.moratorium_years, body.tenure_years)
    get_analyses().update_one({"_id": doc["_id"]}, {"$set": {"dscr": {
        "terms": body.model_dump(), "min_dscr": result.min_dscr, "view": view,
    }}})
    return view


# ── AI assistant ─────────────────────────────────────────────────────────────

def _fact_lines(doc: dict[str, Any]) -> list[str]:
    record = report.record_of(doc["result"])
    if record is None:
        return []
    sc = report.scorecard_for(doc["result"], record, (doc.get("dscr") or {}).get("min_dscr"))
    return report.scorecard_fact_line(sc)


@router.post("/{analysis_id}/assistant/explain")
def explain(analysis_id: str, user: dict = Depends(current_user)) -> dict[str, str]:
    doc = _done(analysis_id, user["user_id"])
    _ai_throttle(user["user_id"])
    text = explain_results(doc["result"], _fact_lines(doc))
    get_analyses().update_one({"_id": doc["_id"]}, {"$set": {"ai.explain": text}})
    return {"text": text}


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@router.post("/{analysis_id}/assistant/ask")
def ask(analysis_id: str, body: AskIn, user: dict = Depends(current_user)) -> dict[str, Any]:
    doc = _done(analysis_id, user["user_id"])
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "Ask a question about this company's financials.")
    _ai_throttle(user["user_id"])
    answer = answer_question(question, doc["result"], _fact_lines(doc))
    entry = {"q": question, "a": answer, "at": datetime.now(timezone.utc).isoformat()}
    get_analyses().update_one({"_id": doc["_id"]}, {"$push": {"ai.qa": {"$each": [entry], "$slice": -QA_KEEP}}})
    return entry


# ── Credit memo ──────────────────────────────────────────────────────────────

@router.get("/{analysis_id}/memo", response_class=HTMLResponse)
def memo(analysis_id: str, download: bool = False, user: dict = Depends(current_user)) -> HTMLResponse:
    doc = _done(analysis_id, user["user_id"])
    state = doc["result"]
    record = report.record_of(state)
    if record is None:
        raise HTTPException(400, "This analysis has no financial record to summarise.")
    min_dscr = (doc.get("dscr") or {}).get("min_dscr")
    sc = report.scorecard_for(state, record, min_dscr)
    credit = state.get("credit_report") or {}
    m = build_memo(
        record, sc, min_dscr=min_dscr,
        dscr_risk=(state.get("dscr_result") or {}).get("risk_level"),
        strengths=credit.get("major_strengths", []), risks=credit.get("major_risks", []),
        recommendation=credit.get("recommendation_narrative", ""),
    )
    headers = dict(MEMO_HEADERS)
    if download:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", m.entity_id)[:40].strip("_") or "company"
        headers["Content-Disposition"] = f'attachment; filename="credit_memo_{safe}.html"'
    return HTMLResponse(render_memo_html(m), headers=headers)
