"""Turn a finished analysis run into the Financial Analysis page's data.

Ports the logic of the Streamlit renderers in finveritas/analysis/page.py
(_render_verdict_banner_v3, _render_credit_scorecard_v3, _render_trends_forecast_v3,
_render_ledger_category, ...) into plain data. All numbers still come from the
deterministic engines; this module only selects and formats them.
"""
from __future__ import annotations

import re
from typing import Any

from finveritas.analysis.metrics.anomaly import detect_anomalies
from finveritas.analysis.metrics.debt_service import DSCRScheduleResult
from finveritas.analysis.metrics.forecast import forecast_field
from finveritas.analysis.metrics.scorecard import CreditScorecard, compute_scorecard
from finveritas.shared.formatting import format_money
from finveritas.shared.meanings import meaning_for
from finveritas.shared.schema import NormalizedCompanyRecord

from api.workspace import clean

LEDGER_SECTIONS = [
    ("saas", "Revenue & SaaS metrics"),
    ("profitability", "Profitability"),
    ("liquidity", "Liquidity"),
    ("working_capital", "Working capital cycle"),
    ("solvency", "Solvency & leverage"),
]

_URL_RE = re.compile(r"https?://\S+|\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b")


def _redact(text: Any) -> str:
    """Pipeline messages can embed exception text with internal URLs/hosts; keep those private."""
    return _URL_RE.sub("[internal address]", str(text))


def redact_strings(obj: Any) -> Any:
    """Apply _redact to every string in a nested structure (used before a result is stored)."""
    if isinstance(obj, str):
        return _redact(obj)
    if isinstance(obj, dict):
        return {k: redact_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_strings(v) for v in obj]
    return obj


# Which DSCR numerator bases the record can support, and how to describe them.
BASIS_LABELS = {
    "cfads": "CFADS — OCF + interest − capex (most conservative)",
    "ocf": "Operating cash flow (+ interest add-back)",
    "ebitda": "EBITDA (earnings proxy)",
    "ebit": "EBIT / operating income",
}


def record_of(state: dict[str, Any]) -> NormalizedCompanyRecord | None:
    data = state.get("company_record")
    if not data:
        return None
    try:
        return NormalizedCompanyRecord(**data)
    except Exception:
        return None


def industry_of(state: dict[str, Any], record: NormalizedCompanyRecord) -> str | None:
    return record.industry or (state.get("company_profile") or {}).get("industry")


def scorecard_for(state: dict[str, Any], record: NormalizedCompanyRecord, min_dscr: float | None) -> CreditScorecard:
    return compute_scorecard(record, industry=industry_of(state, record), min_dscr=min_dscr)


def scorecard_fact_line(sc: CreditScorecard) -> list[str]:
    """Extra grounded line for the AI assistant (mirrors _scorecard_extra_lines)."""
    if sc.composite_score is None:
        return []
    return [f"Credit grade: {sc.grade} ({sc.grade_label}, composite {sc.composite_score:.0f}/100, PD {sc.pd_band})"]


def available_bases(record: NormalizedCompanyRecord) -> list[dict[str, str]]:
    have = {
        "cfads": record.has_field("operating_cash_flow"),
        "ocf": record.has_field("operating_cash_flow"),
        "ebitda": record.has_field("ebitda"),
        "ebit": record.has_field("operating_income"),
    }
    return [{"key": b, "label": BASIS_LABELS[b]} for b in ("cfads", "ocf", "ebitda", "ebit") if have[b]]


def ledger_display(value: float | None, unit: str, currency: str | None = None) -> str:
    if value is None:
        return "N/A"
    if unit == "%":
        return f"{value:.2f}%"
    if unit in ("x", "ratio"):
        return f"{value:.2f}x"
    if unit == "absolute":  # a monetary amount in the statement currency, e.g. net debt
        return format_money(value, currency)
    if unit == "days":
        return f"{value:,.0f} days"
    if unit and unit.isupper() and len(unit) <= 4:  # currency-denominated, e.g. working capital in INR
        return format_money(value, unit)
    return f"{value:,.2f} {unit}".strip()


def _verdict(sc: CreditScorecard, min_dscr: float | None) -> dict[str, Any] | None:
    if sc.composite_score is None:
        return None
    scored = [f for f in sc.factors if f.score is not None]
    watch = min(scored, key=lambda f: f.score) if scored else None
    return {
        "grade": sc.grade,
        "grade_label": sc.grade_label,
        "composite": sc.composite_score,
        "pd_band": sc.pd_band,
        "min_dscr": min_dscr,
        "watch": {"name": watch.name, "note": watch.note} if watch and watch.score < 55 else None,
    }


def _trends(record: NormalizedCompanyRecord) -> dict[str, Any] | None:
    rev = sorted(record.revenue, key=lambda x: x.period)
    if len(rev) < 2:
        return None
    ccy = record.currency
    rows: dict[str, dict[str, Any]] = {p.period: {"period": p.period, "history": p.value} for p in rev}
    fc = forecast_field(record, "revenue", years=3)
    if fc and fc.points:
        last_p, last_v = fc.historical[-1]
        # Join the scenario lines to the last actual point so the chart has no gap.
        rows.setdefault(last_p, {"period": last_p}).update({"base": last_v, "optimistic": last_v, "pessimistic": last_v,
                                                            "band": [last_v, last_v]})
        for pt in fc.points:
            rows[pt.period] = {"period": pt.period, "base": pt.base, "optimistic": pt.optimistic,
                               "pessimistic": pt.pessimistic, "band": [pt.pessimistic, pt.optimistic], "forecast": True}
    revenue = {
        "rows": [rows[k] for k in sorted(rows)],
        "cagr_pct": fc.cagr_pct if fc else None,
        "optimistic_growth_pct": fc.optimistic_growth_pct if fc else None,
        "pessimistic_growth_pct": fc.pessimistic_growth_pct if fc else None,
        "latest_display": format_money(fc.historical[-1][1], ccy) if fc and fc.historical else None,
        "assumptions": fc.assumptions if fc else [],
    }

    op = {p.period: p.value for p in record.operating_income}
    rv = {p.period: p.value for p in record.revenue}
    margins = [{"period": p, "margin": round(op[p] / rv[p] * 100.0, 2)} for p in sorted(rv) if p in op and abs(rv[p]) > 1e-9]
    margin = None
    if len(margins) >= 2:
        first, last = margins[0]["margin"], margins[-1]["margin"]
        margin = {"rows": margins, "first": first, "last": last,
                  "trend": "improving" if last > first else "declining" if last < first else "flat"}
    return {"revenue": revenue, "margin": margin}


def _ledger(state: dict[str, Any]) -> list[dict[str, Any]]:
    entries = (state.get("fact_ledger") or {}).get("entries") or []
    currency = (state.get("fact_ledger") or {}).get("currency") or (state.get("company_record") or {}).get("currency")
    sections = []
    for category, title in LEDGER_SECTIONS:
        rows = []
        for e in entries:
            if e.get("category") != category:
                continue
            value = e.get("value")
            rows.append({
                "metric": e.get("metric"),
                "name": e.get("display_name") or e.get("metric"),
                "value": value,
                "display": "Insufficient data" if value is None and e.get("status") == "INSUFFICIENT_DATA"
                else ledger_display(value, e.get("unit") or "", currency),
                "signal": e.get("risk_signal"),          # PASS | WARN | FAIL | None
                "signal_detail": e.get("risk_detail"),
                "formula": e.get("formula"),
                "meaning": meaning_for(e.get("metric")),
                "period": e.get("period"),
            })
        if rows:
            sections.append({"category": category, "title": title, "rows": rows})
    return sections


def _risk(state: dict[str, Any]) -> dict[str, Any] | None:
    rd = state.get("risk_dashboard")
    if not rd:
        return None
    indicators = rd.get("indicators") or []
    # fail_count / warn_count are properties on the model and are lost by model_dump(), so count here.
    return {
        "overall": rd.get("overall_risk"),
        "fail_count": sum(1 for i in indicators if i.get("status") == "FAIL"),
        "warn_count": sum(1 for i in indicators if i.get("status") == "WARN"),
        "indicators": indicators,
    }


def dscr_view(result: DSCRScheduleResult, ccy: str | None, existing_ds: float, structure: str,
              moratorium: int, tenure: int) -> dict[str, Any]:
    """The DSCR section: headline, plain-language verdict, chart rows, schedule, stress and method."""
    data = clean(result.model_dump())
    for row, dscr in zip(data["schedule"], data["dscr_by_year"]):
        row["dscr"] = dscr
        for k in ("principal", "interest", "total_payment", "opening_balance", "closing_balance"):
            row[f"{k}_display"] = format_money(row[k], ccy, decimals=1)
    m = result.min_dscr
    verdict = None
    if m is not None:
        if m >= 1.5:
            verdict = {"tone": "good", "text": f"Comfortable: even in its tightest year the borrower's cash covers debt service {m:.2f}×."}
        elif m >= 1.0:
            verdict = {"tone": "watch", "text": f"Tight: in year {result.min_dscr_year} coverage falls to {m:.2f}× — little buffer."}
        else:
            verdict = {"tone": "risk", "text": f"Shortfall: in year {result.min_dscr_year} cash covers only {m:.2f}× of debt service (below 1.0× means it cannot fully pay)."}
    method = [
        f"Numerator (cash available): {result.numerator_formula} = {format_money(result.numerator_value, ccy)}",
        "Denominator: scheduled principal + interest each year"
        + (f" + existing debt service {format_money(existing_ds, ccy)}" if existing_ds else ""),
        f"Structure: {structure}" + (f", {moratorium}-year moratorium" if moratorium else ""),
        "Assumption: annual cash held constant across the loan life (conservative — no growth assumed).",
    ]
    return {
        **data,
        "tenure_years": tenure,
        "numerator_display": format_money(result.numerator_value, ccy),
        "verdict": verdict,
        "method": method,
        "breaches": sum(1 for s in result.stress_results if s.breaches_1x),
    }


def build(doc: dict[str, Any]) -> dict[str, Any]:
    """The full report for a completed run."""
    state = doc.get("result") or {}
    record = record_of(state)
    dscr = doc.get("dscr") or {}
    min_dscr = dscr.get("min_dscr")
    credit = state.get("credit_report") or {}
    findings = [f for f in (state.get("qualitative_findings") or [])
                if f != "No qualitative corporate intelligence available for this company."]
    peers = (state.get("peer_comparison") or {}).get("peers") or []

    out: dict[str, Any] = {
        "entity": doc.get("entity"),
        "currency": record.currency if record else None,
        "industry": industry_of(state, record) if record else None,
        "has_record": record is not None,
        "ledger": _ledger(state),
        "peers": peers,
        # metric -> {target, peer_median, percentile}: lets the UI chart the company against its peers.
        "peer_metrics": (state.get("peer_comparison") or {}).get("comparison_metrics") or {},
        "risk": _risk(state),
        "credit_report": {
            "strengths": credit.get("major_strengths") or [],
            "risks": credit.get("major_risks") or [],
            "narrative": credit.get("recommendation_narrative") or "",
            "disclaimer": credit.get("disclaimer") or "",
        } if credit else None,
        "qualitative_findings": findings,
        "workflow_log": [_redact(line) for line in state.get("workflow_log") or []],
        "errors": [_redact(e) for e in state.get("errors") or []],
        "dscr": dscr.get("view"),
        "dscr_terms": dscr.get("terms"),
        "ai": doc.get("ai") or {"explain": None, "qa": []},
        "verdict": None, "scorecard": None, "anomalies": None, "trends": None, "dscr_bases": [],
    }
    if record is None:
        return out

    sc = scorecard_for(state, record, min_dscr)
    anomalies = detect_anomalies(record)
    out.update({
        "verdict": _verdict(sc, min_dscr),
        "scorecard": clean(sc.model_dump()) if sc.composite_score is not None else None,
        "anomalies": {
            "critical": anomalies.critical_count,
            "warning": anomalies.warning_count,
            "items": clean([a.model_dump() for a in anomalies.anomalies]),
        },
        "trends": _trends(record),
        "dscr_bases": available_bases(record),
    })
    return out


def raw_state(doc: dict[str, Any]) -> dict[str, Any]:
    """The audit view: everything the pipeline produced (configuration was stripped before storage)."""
    state = dict(doc.get("result") or {})
    if "workflow_log" in state:
        state["workflow_log"] = [_redact(line) for line in state["workflow_log"]]
    if "errors" in state:
        state["errors"] = [_redact(e) for e in state["errors"]]
    return state
