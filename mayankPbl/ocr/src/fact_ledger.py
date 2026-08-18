"""Immutable Fact Ledger (V2)

Generates a structured, immutable JSON contract from the Deterministic
Metrics Engine output. This ledger is the SINGLE SOURCE OF TRUTH that
all downstream agents (Forecasting, Competitive, Risk, Credit, etc.)
must read from.

Key principles:
- Once generated, the ledger is immutable for that analysis run.
- All values originate from Python computation — never from the LLM.
- Source metadata is attached for traceability.
- The LLM reads FROM the ledger; it never writes TO it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.metrics_engine import compute_all_metrics


def build_fact_ledger(
    payload: dict[str, Any],
    source_type: str = "unknown",
    source_label: str = "",
) -> dict[str, Any]:
    """Build an immutable fact ledger from a FinVeritas payload.

    Args:
        payload: The OCR/ingestion output dict with 'entity' and 'time_series'.
        source_type: "bloomberg_pdf", "ticker", or "csv".
        source_label: Human-readable source identifier (filename, ticker symbol, etc.).

    Returns:
        A structured fact ledger dict with:
        - metadata (entity, timestamps, source)
        - all 12 metric categories from the metrics engine
        - risk flags
        - availability summary
    """
    # Compute all metrics deterministically
    metrics = compute_all_metrics(payload)

    entity_id = metrics.get("entity", "UNKNOWN")
    now = datetime.now(timezone.utc).isoformat()

    ledger: dict[str, Any] = {
        # ── Metadata ──────────────────────────────────────────────────────
        "ledger_version": "2.0",
        "computed_at": now,
        "immutable": True,

        "entity": {
            "entity_id": entity_id,
            "source_type": source_type,
            "source_label": source_label,
        },

        "period_coverage": {
            "periods": metrics.get("periods", []),
            "period_count": metrics.get("period_count", 0),
        },

        # ── All 12 Metric Categories ─────────────────────────────────────
        "metrics": {
            "revenue_intelligence": metrics.get("revenue_intelligence", {}),
            "cost_intelligence": metrics.get("cost_intelligence", {}),
            "profitability_intelligence": metrics.get("profitability_intelligence", {}),
            "liquidity_intelligence": metrics.get("liquidity_intelligence", {}),
            "solvency_intelligence": metrics.get("solvency_intelligence", {}),
            "debt_servicing_intelligence": metrics.get("debt_servicing_intelligence", {}),
            "efficiency_intelligence": metrics.get("efficiency_intelligence", {}),
            "return_intelligence": metrics.get("return_intelligence", {}),
            "cash_flow_intelligence": metrics.get("cash_flow_intelligence", {}),
            "growth_intelligence": metrics.get("growth_intelligence", {}),
            "trend_intelligence": metrics.get("trend_intelligence", {}),
            "risk_intelligence": metrics.get("risk_intelligence", {}),
        },

        # ── Availability Summary ─────────────────────────────────────────
        "availability": metrics.get("_availability_summary", {}),

        # ── Source Traceability ───────────────────────────────────────────
        "source_metadata": {
            "source_type": source_type,
            "source_label": source_label,
            "retrieved_at": now,
            "computation_engine": "FinVeritas Deterministic Metrics Engine v2.0",
            "llm_involvement": "NONE — all values are Python-computed",
        },
    }

    return ledger


def save_fact_ledger(
    ledger: dict[str, Any],
    output_dir: str | Path = "output",
) -> Path:
    """Persist the fact ledger to disk as immutable JSON.

    Args:
        ledger: The fact ledger dict from build_fact_ledger().
        output_dir: Directory to write to (default: output/).

    Returns:
        Path to the written file.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    entity = ledger.get("entity", {}).get("entity_id", "UNKNOWN")
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in entity).strip().replace(" ", "_")
    filename = f"{safe_name}_fact_ledger.json"

    path = out / filename
    path.write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    return path


def summarize_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    """Generate a human-readable summary of the fact ledger.

    Useful for the UI to show a quick overview without rendering
    the full ledger JSON.
    """
    metrics = ledger.get("metrics", {})
    availability = ledger.get("availability", {})

    available_count = sum(1 for v in availability.values() if v)
    total_count = len(availability)

    # Extract key headline metrics
    headlines: list[dict[str, Any]] = []

    rev = metrics.get("revenue_intelligence", {})
    if rev.get("available"):
        headlines.append({
            "label": "Revenue Growth (CAGR)",
            "value": rev.get("cagr_pct"),
            "format": "pct",
        })

    prof = metrics.get("profitability_intelligence", {})
    if prof.get("available"):
        if "net_margin_pct" in prof:
            headlines.append({
                "label": "Net Margin",
                "value": prof["net_margin_pct"],
                "format": "pct",
            })
        if "ebitda_margin_pct" in prof:
            headlines.append({
                "label": "EBITDA Margin",
                "value": prof["ebitda_margin_pct"],
                "format": "pct",
            })

    liq = metrics.get("liquidity_intelligence", {})
    if liq.get("available"):
        headlines.append({
            "label": "Current Ratio",
            "value": liq.get("current_ratio_latest"),
            "format": "ratio",
        })

    solv = metrics.get("solvency_intelligence", {})
    if solv.get("available"):
        headlines.append({
            "label": "Debt/Equity",
            "value": solv.get("debt_to_equity_latest"),
            "format": "ratio",
        })

    ret = metrics.get("return_intelligence", {})
    if ret.get("available"):
        if "roe_pct_latest" in ret:
            headlines.append({
                "label": "ROE",
                "value": ret["roe_pct_latest"],
                "format": "pct",
            })

    risk = metrics.get("risk_intelligence", {})
    risk_summary = risk.get("summary", {})

    return {
        "entity": ledger.get("entity", {}).get("entity_id", "—"),
        "computed_at": ledger.get("computed_at", "—"),
        "categories_available": available_count,
        "categories_total": total_count,
        "headlines": headlines,
        "risk_summary": risk_summary,
    }
