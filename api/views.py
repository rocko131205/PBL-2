"""Pure functions that turn a stored payload into what the Upload page shows.

Ported from the Streamlit helpers (`render_metric_cards`, `_preview_df`,
`_available_fields`, `_render_agent_status_badges`, ...). No database or HTTP here,
so they are easy to unit-test.
"""
from __future__ import annotations

import copy
import math
import re
from datetime import datetime, timezone
from typing import Any

from finveritas.ingestion.scale import SCALE_MULTIPLIERS
from finveritas.shared.formatting import format_money

CARD_FIELDS = [
    ("revenue", "Revenue"),
    ("total_assets", "Total assets"),
    ("total_liabilities", "Total liabilities"),
    ("equity", "Equity"),
]
PREVIEW_FIELDS = ["revenue", "total_assets", "total_liabilities", "equity"]
LIQUIDITY_REQUIRED = {"current_assets", "current_liabilities", "total_assets", "total_liabilities", "equity"}
BALANCE_SHEET_REQUIRED = {"total_assets", "total_liabilities", "equity"}

SCALE_OPTIONS = [
    {"key": "absolute", "label": "Absolute (as-is)", "multiplier": SCALE_MULTIPLIERS["absolute"]},
    {"key": "thousand", "label": "Thousands", "multiplier": SCALE_MULTIPLIERS["thousand"]},
    {"key": "lakh", "label": "Lakhs", "multiplier": SCALE_MULTIPLIERS["lakh"]},
    {"key": "million", "label": "Millions", "multiplier": SCALE_MULTIPLIERS["million"]},
    {"key": "crore", "label": "Crores", "multiplier": SCALE_MULTIPLIERS["crore"]},
    {"key": "billion", "label": "Billions", "multiplier": SCALE_MULTIPLIERS["billion"]},
]
VALID_MULTIPLIERS = {o["multiplier"] for o in SCALE_OPTIONS}

_PERIOD_RE = re.compile(r"^(\d{4})-(FY|Q[1-4])$")


def available_fields(payload: dict[str, Any]) -> set[str]:
    ts = payload.get("time_series") or {}
    return {k for k, v in ts.items() if isinstance(v, list) and len(v) > 0}


def period_key(period: str) -> tuple[int, int]:
    """Chronological sort key: within a year the quarters come first and the full-year figure last."""
    m = _PERIOD_RE.match(period)
    if not m:
        return (0, 0)
    tag = m.group(2)
    return (int(m.group(1)), 5 if tag == "FY" else int(tag[1:]))


def series_rows(payload: dict[str, Any], field: str) -> list[tuple[str, float]]:
    """All (period, value) pairs for a field, chronologically sorted."""
    rows = []
    for item in (payload.get("time_series") or {}).get(field) or []:
        if isinstance(item, dict) and item.get("value") is not None:
            try:
                rows.append((str(item.get("period", "—")), float(item["value"])))
            except (TypeError, ValueError):
                continue
    rows.sort(key=lambda r: period_key(r[0]))
    return rows


def latest_value(rows: list[tuple[str, float]]) -> tuple[float | None, str]:
    """Most recent actual figure — periods in the future are projections and are skipped."""
    year_now = datetime.now(timezone.utc).year
    for period, value in reversed(rows):
        try:
            if int(period[:4]) > year_now:
                continue
        except ValueError:
            pass
        return value, period
    if rows:
        return rows[-1][1], rows[-1][0]
    return None, "—"


def periods_in(payload: dict[str, Any]) -> list[str]:
    """Every distinct period across all fields, oldest first."""
    found: set[str] = set()
    for entries in (payload.get("time_series") or {}).values():
        if isinstance(entries, list):
            for e in entries:
                if isinstance(e, dict) and e.get("period"):
                    found.add(str(e["period"]))

    return sorted(found, key=period_key)


def metric_cards(display_payload: dict[str, Any]) -> list[dict[str, Any]]:
    currency = (display_payload.get("entity") or {}).get("currency")
    cards = []
    for field, label in CARD_FIELDS:
        rows = series_rows(display_payload, field)
        value, period = latest_value(rows)
        # Change is measured up to the figure the card displays, not past it into projected periods.
        shown = [r for r in rows if period_key(r[0]) <= period_key(period)] or rows
        change = None
        if len(shown) >= 2 and abs(shown[0][1]) > 1e-9:
            change = (shown[-1][1] - shown[0][1]) / abs(shown[0][1]) * 100.0
        cards.append({
            "field": field,
            "label": label,
            "period": period,
            "value": value,
            "display": format_money(value, currency),
            "change_pct": change,
            "series": [{"period": p, "value": v, "display": format_money(v, currency)} for p, v in rows],
        })
    return cards


def preview_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Last five periods of each headline field, for the 'raw data' table."""
    out: list[dict[str, Any]] = []
    for field in PREVIEW_FIELDS:
        for period, value in series_rows(payload, field)[-5:]:
            out.append({"field": field, "period": period, "value": value})
    return out


def readiness(payload: dict[str, Any]) -> dict[str, Any]:
    avail = available_fields(payload)
    missing_liq = sorted(LIQUIDITY_REQUIRED - avail)
    missing_bs = sorted(BALANCE_SHEET_REQUIRED - avail)
    missing = sorted(set(missing_liq) | set(missing_bs))
    skipped = []
    if missing_liq:
        skipped.append("Liquidity agent")
    if missing_bs:
        skipped.append("Balance sheet agent")
    if skipped:
        skipped.append("Cross-reference agent")
    return {
        "missing_fields": missing,
        "complete": not missing,
        "skipped_agents": skipped,
        "agents": [
            {"key": "revenue", "label": "Revenue", "ready": "revenue" in avail},
            {"key": "liquidity", "label": "Liquidity", "ready": not missing_liq},
            {"key": "solvency", "label": "Solvency", "ready": not missing_bs},
            {"key": "cash_flow", "label": "Cash flow", "ready": "operating_cash_flow" in avail},
            {"key": "credit_score", "label": "Credit score", "ready": "revenue" in avail and not missing_bs},
        ],
    }


def patch_field(payload: dict[str, Any], field: str, period_values: dict[str, float]) -> dict[str, Any]:
    """Return a copy with `field` extended/overwritten by user-supplied period → value pairs."""
    out = copy.deepcopy(payload)
    ts = out.setdefault("time_series", {})
    existing = {e["period"]: e["value"] for e in ts.get(field, []) if isinstance(e, dict)}
    existing.update(period_values)
    ts[field] = sorted(({"period": k, "value": v} for k, v in existing.items()), key=lambda x: x["period"])
    return out


def parse_amount(raw: Any) -> float:
    """A user-typed number ('1,50,000', '150000.5'). Raises ValueError if not a finite number."""
    value = float(str(raw).replace(",", "").strip())
    if not math.isfinite(value):
        raise ValueError("not finite")
    return value
