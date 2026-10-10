"""Loading data (Bloomberg PDF / listed ticker / private CSV) and reviewing it before analysis."""
from __future__ import annotations

import os
import re
import secrets
import sys
import traceback
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api import views, workspace
from api.deps import current_user
from finveritas.ingestion.credibility import run_verification
from finveritas.ingestion.pdf.loader import parse_pdf_to_json
from finveritas.ingestion.spreadsheet import get_template_csv, load_private_company_data
from finveritas.ingestion.supplemental import auto_fetch_missing_fields, fetch_latest_earnings_call_transcript
from finveritas.ingestion.ticker import fetch_by_ticker
from finveritas.security import audit, ratelimit
from finveritas.security.uploads import (
    MAX_PDF_BYTES, MAX_PDF_FILES, MAX_SHEET_BYTES, UploadRejected, validate_pdf_batch, validate_spreadsheet,
)

router = APIRouter(prefix="/api", tags=["ingest"])

# Ticker and file ingestion call third-party services and heavy parsers: cap them per user.
INGEST_MAX = 20
INGEST_WINDOW_MINUTES = 10

# Interpolated into third-party URLs (FMP / Alpha Vantage), so the format is allow-listed.
_TICKER_RE = re.compile(r"\^?[A-Z0-9][A-Z0-9.\-=]{0,14}")
CURRENCIES = ["INR", "USD", "EUR", "GBP", "JPY", "SGD", "AED"]


def _fmp_key() -> str:
    return os.getenv("FMP_API_KEY", "").strip()


def _av_key() -> str:
    return os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()


def _fail(context: str, exc: Exception) -> HTTPException:
    """A safe message for the user; full details (with a reference id) go to the server log (CWE-209)."""
    ref = secrets.token_hex(4)
    print(f"[error {ref}] {context}: {type(exc).__name__}: {exc}\n{traceback.format_exc()}", file=sys.stderr)
    if isinstance(exc, (UploadRejected, ValueError)):
        return HTTPException(422, f"{context}: {exc}")
    return HTTPException(500, f"{context}. An unexpected error occurred (reference {ref}).")


def _throttle(user_id: str) -> None:
    key = f"ingest:{user_id}"
    if ratelimit.is_limited(key, INGEST_MAX, INGEST_WINDOW_MINUTES):
        raise HTTPException(429, "You're loading data too quickly. Please wait a few minutes.")
    ratelimit.record(key, INGEST_WINDOW_MINUTES)


def _read_limited(upload: UploadFile, limit: int, label: str) -> bytes:
    """Read at most limit+1 bytes so an oversized body is rejected without buffering all of it."""
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise UploadRejected(f"'{upload.filename}' exceeds the {limit // (1024 * 1024)} MB {label} limit.")
    return data


def _view(user_id: str) -> dict[str, Any]:
    return workspace.view(workspace.load(user_id), fmp_configured=bool(_fmp_key()), av_configured=bool(_av_key()))


def _require(user_id: str) -> dict[str, Any]:
    doc = workspace.load(user_id)
    if not doc:
        raise HTTPException(404, "No data loaded yet. Upload a statement first.")
    return doc


# ── Loading data ─────────────────────────────────────────────────────────────

@router.post("/ingest/pdf")
def ingest_pdf(files: list[UploadFile] = File(...), user: dict = Depends(current_user)) -> dict[str, Any]:
    if not files:
        raise HTTPException(422, "Choose at least one PDF.")
    if len(files) > MAX_PDF_FILES:
        raise HTTPException(422, f"Upload at most {MAX_PDF_FILES} PDFs at a time.")
    _throttle(user["user_id"])
    try:
        raw = [(_read_limited(f, MAX_PDF_BYTES, "PDF"), f.filename or "") for f in files]
        validated = validate_pdf_batch(raw)
    except UploadRejected as exc:
        audit.log_event(audit.UPLOAD_REJECTED, user_id=user["user_id"], detail={"kind": "pdf", "reason": str(exc)})
        raise HTTPException(422, str(exc)) from None
    try:
        payload, _, _ = parse_pdf_to_json(uploads=[(v.data, v.filename) for v in validated])
    except Exception as exc:
        raise _fail("Could not read the PDF(s)", exc) from None
    workspace.replace(user["user_id"], source="pdf", payload=payload,
                      source_label=f"{len(validated)} Bloomberg PDF(s)")
    return _view(user["user_id"])


class TickerIn(BaseModel):
    ticker: str = Field(max_length=32)


@router.post("/ingest/ticker")
def ingest_ticker(body: TickerIn, user: dict = Depends(current_user)) -> dict[str, Any]:
    ticker = body.ticker.strip().upper()
    if not ticker:
        raise HTTPException(422, "Enter a ticker symbol first.")
    if not _TICKER_RE.fullmatch(ticker):
        raise HTTPException(422, "Invalid ticker format. Use letters, digits, '.', '-' (e.g. INFY.NS, BRK-B).")
    _throttle(user["user_id"])
    try:
        payload = fetch_by_ticker(ticker)
        if payload.get("entity") is None:
            payload["entity"] = {}
        transcript = ""
        if _fmp_key():
            try:
                transcript = fetch_latest_earnings_call_transcript(ticker, _fmp_key())
            except Exception:
                transcript = ""  # soft context only — never block the load
        payload["entity"]["qualitative_context"] = transcript
    except Exception as exc:
        raise _fail("Could not fetch that ticker", exc) from None
    workspace.replace(user["user_id"], source="ticker", payload=payload, ticker=ticker,
                      source_label=f"yfinance · {ticker}")
    return _view(user["user_id"])


@router.post("/ingest/csv")
def ingest_csv(
    file: UploadFile = File(...),
    company_name: str = Form(..., max_length=100),
    currency: str = Form("INR"),
    user: dict = Depends(current_user),
) -> dict[str, Any]:
    name = company_name.strip()
    if not name:
        raise HTTPException(422, "Please enter the company name before loading.")
    if currency not in CURRENCIES:
        raise HTTPException(422, "Unsupported currency.")
    _throttle(user["user_id"])
    try:
        sheet = validate_spreadsheet(_read_limited(file, MAX_SHEET_BYTES, "spreadsheet"), file.filename or "")
    except UploadRejected as exc:
        audit.log_event(audit.UPLOAD_REJECTED, user_id=user["user_id"], detail={"kind": "spreadsheet", "reason": str(exc)})
        raise HTTPException(422, str(exc)) from None
    try:
        payload = load_private_company_data(
            file_bytes=sheet.data, filename=sheet.filename, company_name=name, currency=currency,
        )
    except Exception as exc:
        raise _fail("Could not read the spreadsheet", exc) from None
    workspace.replace(user["user_id"], source="csv", payload=payload,
                      source_label=f"Private upload · {sheet.filename}")
    return _view(user["user_id"])


@router.get("/ingest/csv-template")
def csv_template(_: dict = Depends(current_user)) -> Response:
    return Response(
        get_template_csv(), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="private_company_template.csv"'},
    )


# ── Reviewing the loaded data ────────────────────────────────────────────────

@router.get("/workspace")
def get_workspace(user: dict = Depends(current_user)) -> dict[str, Any]:
    return _view(user["user_id"])


@router.delete("/workspace", status_code=204)
def clear_workspace(user: dict = Depends(current_user)) -> Response:
    workspace.clear(user["user_id"])
    return Response(status_code=204)


class ScaleIn(BaseModel):
    multiplier: float


@router.put("/workspace/scale")
def set_scale(body: ScaleIn, user: dict = Depends(current_user)) -> dict[str, Any]:
    doc = _require(user["user_id"])
    if doc["source"] == "ticker":
        raise HTTPException(400, "Ticker data is already in absolute units; no scale applies.")
    if body.multiplier not in views.VALID_MULTIPLIERS:
        raise HTTPException(422, "Unsupported scale.")
    # Anything computed at the old scale (the credibility report, an analysis) no longer describes this data.
    workspace.update(user["user_id"], {"scale": body.multiplier}, unset=["analysis_id", "credibility"])
    return _view(user["user_id"])


class QualitativeIn(BaseModel):
    text: str = Field(max_length=20000)


@router.put("/workspace/qualitative")
def set_qualitative(body: QualitativeIn, user: dict = Depends(current_user)) -> dict[str, str]:
    doc = _require(user["user_id"])
    payload = doc["payload"]
    payload.setdefault("entity", {})["qualitative_context"] = body.text
    workspace.update(user["user_id"], {"payload": payload})
    return {"status": "saved"}


@router.get("/workspace/credibility")
def get_credibility(user: dict = Depends(current_user)) -> dict[str, Any]:
    """Run the credibility checks (cached until the data changes — they can call external APIs)."""
    doc = _require(user["user_id"])
    if doc.get("credibility"):
        return doc["credibility"]
    source = {"pdf": "bloomberg_pdf", "ticker": "ticker", "csv": "csv"}[doc["source"]]
    try:
        # Same scaled data the analysis runs on, so the score shown here matches the one in file history.
        report = run_verification(source=source, payload=workspace.display_payload(doc), ticker=doc.get("ticker"),
                                  fmp_api_key=_fmp_key())
    except Exception as exc:
        raise _fail("Credibility checks failed", exc) from None
    result = {
        "score": report.score,
        "confidence": report.confidence,
        "source": report.source,
        "entity": report.entity,
        "checks": [{"name": c.name, "status": c.status, "detail": c.detail, "weight": c.weight} for c in report.checks],
    }
    workspace.update(user["user_id"], {"credibility": result})
    return result


# ── Filling in missing fields ────────────────────────────────────────────────

class AutofetchIn(BaseModel):
    provider: str


@router.post("/workspace/supplement/autofetch")
def autofetch(body: AutofetchIn, user: dict = Depends(current_user)) -> dict[str, Any]:
    doc = _require(user["user_id"])
    if doc["source"] != "ticker" or not doc.get("ticker"):
        raise HTTPException(400, "Auto-fetch is only available for ticker data.")
    if body.provider not in {"fmp", "alphavantage"}:
        raise HTTPException(422, "Unknown provider.")
    key = _fmp_key() if body.provider == "fmp" else _av_key()
    if not key:
        raise HTTPException(400, "This data provider isn't configured on the server.")
    missing = set(views.readiness(doc["payload"])["missing_fields"])
    _throttle(user["user_id"])
    resolved, resolved_fields, errors = auto_fetch_missing_fields(
        ticker=doc["ticker"], missing_fields=missing,
        fmp_api_key=key if body.provider == "fmp" else None,
        av_api_key=key if body.provider == "alphavantage" else None,
    )
    return {
        "resolved_fields": resolved_fields,
        "values": {f: {e["period"]: e["value"] for e in series} for f, series in workspace.clean(resolved).items()},
        # Provider errors can echo request URLs; keep them out of the response.
        "errors": [f"{e.split(':')[0]} could not be reached." for e in errors],
    }


class SupplementIn(BaseModel):
    values: dict[str, dict[str, str | float | None]]


@router.post("/workspace/supplement/apply")
def apply_supplement(body: SupplementIn, user: dict = Depends(current_user)) -> dict[str, Any]:
    doc = _require(user["user_id"])
    payload = doc["payload"]
    allowed_fields = set(views.readiness(payload)["missing_fields"])
    allowed_periods = set(views.periods_in(payload))

    errors: dict[str, str] = {}
    patches: dict[str, dict[str, float]] = {}
    for field, per_period in body.values.items():
        if field not in allowed_fields:
            errors[field] = "This field can't be supplied."
            continue
        for period, raw in per_period.items():
            if raw is None or str(raw).strip() == "":
                continue
            if period not in allowed_periods:
                errors[f"{field}|{period}"] = "Unknown period."
                continue
            try:
                patches.setdefault(field, {})[period] = views.parse_amount(raw)
            except ValueError:
                errors[f"{field}|{period}"] = f"'{raw}' is not a number."
    if errors:
        raise HTTPException(422, detail={"errors": errors})
    if not patches:
        raise HTTPException(422, "No values were entered. Fill in at least one field.")

    for field, period_values in patches.items():
        payload = views.patch_field(payload, field, period_values)
    # New data invalidates the cached credibility report and any analysis of the old data.
    workspace.update(user["user_id"], {"payload": workspace.clean(payload)}, unset=["credibility", "analysis_id"])
    return _view(user["user_id"])
