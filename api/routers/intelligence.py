"""On-demand intelligence agents for a finished analysis: forecast check, competitive benchmark,
working-capital credit, geography and governance.

Each endpoint runs a deterministic Python core and (optionally) asks the LLM to narrate the result.
Results are saved on the analysis so they are still there after a reload. Everything is scoped to the
caller's own analysis, and the LLM-backed calls share the assistant's per-user rate limit.
"""
from __future__ import annotations

import math
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from api import report, workspace
from api.deps import current_user
from api.routers.analysis import _ai_throttle, _done
from api.workspace import clean
from finveritas.analysis.metrics.extended import build_extended_ledger
from finveritas.analysis.metrics.extended.domain import DOMAIN_INPUT_FIELDS, SECTORS
from finveritas.auth.db import get_analyses
from finveritas.intelligence import competitive, credit, forecast_validation, geography, governance
from finveritas.shared.schema import FinancialFactLedger, NormalizedCompanyRecord

router = APIRouter(prefix="/api", tags=["intelligence"])

_PERIOD = re.compile(r"^\d{4}-(FY|Q[1-4])$")
_REGION_OK = re.compile(r"[^A-Za-z0-9 &/,'()\-]")   # no '.' or '$': these become stored document keys
_NAME_OK = re.compile(r"[^A-Za-z .'\-]")
_MAX_ABS = 1e18


def _record(doc: dict[str, Any]) -> NormalizedCompanyRecord:
    record = report.record_of(doc["result"])
    if record is None:
        raise HTTPException(400, "This analysis has no financial record to work from.")
    return record


def _save(doc: dict[str, Any], key: str, result: dict[str, Any]) -> dict[str, Any]:
    result = clean(result)
    get_analyses().update_one({"_id": doc["_id"]}, {"$set": {f"intelligence.{key}": result}})
    return result


def _call(user: dict, doc: dict[str, Any], key: str, fn) -> dict[str, Any]:
    """Throttle, run the agent, never leak internals, and persist the result."""
    _ai_throttle(user["user_id"])
    try:
        return _save(doc, key, fn())
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception as exc:
        import secrets
        import sys
        ref = secrets.token_hex(4)
        print(f"[intelligence {key} {ref}] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise HTTPException(502, f"That analysis couldn't be completed (reference {ref}).") from None


# ── Sector (applies to the next analysis run) ────────────────────────────────

class SectorIn(BaseModel):
    sector: Literal["general", "saas", "banking", "retail", "manufacturing"] = "general"
    domain_inputs: dict[str, float] = Field(default_factory=dict, max_length=20)

    @field_validator("domain_inputs")
    @classmethod
    def _finite(cls, v: dict[str, float]) -> dict[str, float]:
        for k, x in v.items():
            if not math.isfinite(x) or abs(x) > _MAX_ABS:
                raise ValueError(f"'{k}' must be a reasonable number.")
        return v


@router.get("/sectors")
def sectors(user: dict = Depends(current_user)) -> dict[str, Any]:
    return {"sectors": list(SECTORS), "input_fields": DOMAIN_INPUT_FIELDS}


@router.put("/workspace/sector")
def set_sector(body: SectorIn, user: dict = Depends(current_user)) -> dict[str, str]:
    ws = workspace.load(user["user_id"])
    if not ws:
        raise HTTPException(400, "Load a statement on the Upload page first.")
    allowed = set(DOMAIN_INPUT_FIELDS.get(body.sector, []))
    unknown = sorted(set(body.domain_inputs) - allowed)
    if unknown:
        raise HTTPException(422, f"Unknown input(s) for {body.sector}: {', '.join(unknown)}.")
    payload = ws["payload"]
    entity = payload.setdefault("entity", {})
    entity["sector"] = body.sector
    entity["domain_inputs"] = body.domain_inputs
    workspace.update(user["user_id"], {"payload": payload})
    return {"status": "saved"}


# ── Forecast assumption check ────────────────────────────────────────────────

class ForecastIn(BaseModel):
    metric: Literal["revenue", "ebitda", "pat"] = "revenue"
    assumption_pct: float = Field(ge=-100, le=500)
    periods_ahead: int = Field(3, ge=1, le=10)
    guidance_low: float | None = Field(None, ge=-100, le=500)
    guidance_high: float | None = Field(None, ge=-100, le=500)
    sector_benchmark_pct: float | None = Field(None, ge=-100, le=500)


@router.post("/analysis/{analysis_id}/forecast/validate")
def validate_forecast(analysis_id: str, body: ForecastIn, user: dict = Depends(current_user)) -> dict[str, Any]:
    doc = _done(analysis_id, user["user_id"])
    record = _record(doc)
    if body.guidance_low is not None and body.guidance_high is not None and body.guidance_low > body.guidance_high:
        raise HTTPException(422, "Guidance low can't be above guidance high.")
    return _call(user, doc, "forecast", lambda: forecast_validation.run(
        record, metric=body.metric, assumption_pct=body.assumption_pct, periods_ahead=body.periods_ahead,
        guidance_low=body.guidance_low, guidance_high=body.guidance_high,
        sector_benchmark_pct=body.sector_benchmark_pct))


# ── Competitive benchmark ────────────────────────────────────────────────────

class CompetitiveIn(BaseModel):
    tickers: list[str] = Field(default_factory=list, max_length=competitive.MAX_PEERS)


@router.post("/analysis/{analysis_id}/competitive")
def run_competitive(analysis_id: str, body: CompetitiveIn, user: dict = Depends(current_user)) -> dict[str, Any]:
    doc = _done(analysis_id, user["user_id"])
    record = _record(doc)
    tickers = [t for t in body.tickers if t.strip()]
    if not tickers:  # default to the peers the workflow already identified
        peers = (doc["result"].get("peer_comparison") or {}).get("peers") or []
        tickers = [p["ticker"] for p in peers if p.get("ticker")]
    bad = [t for t in tickers if not competitive.TICKER_RE.match(t.strip().upper())]
    if bad:
        raise HTTPException(422, f"Not a valid ticker symbol: {bad[0][:20]}")
    return _call(user, doc, "competitive", lambda: competitive.run(record, tickers))


# ── Working-capital credit narrative ─────────────────────────────────────────

@router.post("/analysis/{analysis_id}/credit/narrate")
def narrate_credit(analysis_id: str, user: dict = Depends(current_user)) -> dict[str, Any]:
    doc = _done(analysis_id, user["user_id"])
    record = _record(doc)
    state = doc["result"]
    ledger = FinancialFactLedger(**state["extended_ledger"]) if state.get("extended_ledger") \
        else build_extended_ledger(record)[0]
    return _call(user, doc, "credit", lambda: credit.run(ledger.entries, record.currency))


# ── Geography ────────────────────────────────────────────────────────────────

class GeoExtractIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    period: str

    @field_validator("period")
    @classmethod
    def _period(cls, v: str) -> str:
        if not _PERIOD.match(v.strip().upper()):
            raise ValueError("Use a period like 2024-FY or 2024-Q2.")
        return v.strip().upper()


@router.post("/analysis/{analysis_id}/geography/extract")
def extract_geography(analysis_id: str, body: GeoExtractIn, user: dict = Depends(current_user)) -> dict[str, Any]:
    """Best-effort read of pasted segment-note text. Returned for the user to confirm; nothing is saved."""
    _done(analysis_id, user["user_id"])
    return {"segments": geography.extract_regional_revenue(body.text, body.period)}


class GeoIn(BaseModel):
    segments: dict[str, dict[str, float]]

    @field_validator("segments")
    @classmethod
    def _check(cls, v: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        if not v or len(v) > geography.MAX_REGIONS:
            raise ValueError(f"Enter between 1 and {geography.MAX_REGIONS} regions.")
        out: dict[str, dict[str, float]] = {}
        for region, series in v.items():
            name = _REGION_OK.sub("", region).strip()[:60]
            if not name:
                raise ValueError("Every region needs a name.")
            if not series or len(series) > geography.MAX_PERIODS:
                raise ValueError(f"'{name}' needs 1 to {geography.MAX_PERIODS} periods.")
            clean_series: dict[str, float] = {}
            for period, value in series.items():
                p = period.strip().upper()
                if not _PERIOD.match(p):
                    raise ValueError(f"'{period}' isn't a valid period (use 2024-FY or 2024-Q2).")
                if not math.isfinite(value) or abs(value) > _MAX_ABS:
                    raise ValueError(f"'{name}' {p}: enter a reasonable number.")
                clean_series[p] = float(value)
            out[name] = clean_series
        return out


@router.post("/analysis/{analysis_id}/geography")
def run_geography(analysis_id: str, body: GeoIn, user: dict = Depends(current_user)) -> dict[str, Any]:
    doc = _done(analysis_id, user["user_id"])
    record = _record(doc)
    return _call(user, doc, "geography", lambda: {**geography.run(record, body.segments), "input": body.segments})


# ── Governance ───────────────────────────────────────────────────────────────

class GovExtractIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


@router.post("/analysis/{analysis_id}/governance/extract")
def extract_directors(analysis_id: str, body: GovExtractIn, user: dict = Depends(current_user)) -> dict[str, Any]:
    """Best-effort director/DIN extraction from pasted filing text, for the user to confirm."""
    _done(analysis_id, user["user_id"])
    return {"directors": governance.extract_directors(body.text)[:governance.MAX_DIRECTORS]}


class Director(BaseModel):
    name: str = Field("", max_length=80)
    din: str = Field("", max_length=8)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return re.sub(r"\s+", " ", _NAME_OK.sub("", v)).strip()

    @field_validator("din")
    @classmethod
    def _din(cls, v: str) -> str:
        v = v.strip()
        if v and not re.fullmatch(r"\d{8}", v):
            raise ValueError("A DIN is 8 digits.")
        return v


class GovIn(BaseModel):
    directors: list[Director] = Field(min_length=1, max_length=governance.MAX_DIRECTORS)


@router.post("/analysis/{analysis_id}/governance")
def run_governance(analysis_id: str, body: GovIn, user: dict = Depends(current_user)) -> dict[str, Any]:
    doc = _done(analysis_id, user["user_id"])
    record = _record(doc)
    people = [d.model_dump() for d in body.directors if d.name or d.din]
    if not people:
        raise HTTPException(422, "Enter at least one director name or DIN.")
    return _call(user, doc, "governance", lambda: governance.run(record, people))
