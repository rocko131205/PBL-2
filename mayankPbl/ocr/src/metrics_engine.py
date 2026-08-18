"""Deterministic Metrics Engine (V2)

Centralized financial metrics computation across 12 categories.
All numeric computations happen in Python (pandas/numpy).
The LLM is NEVER used for arithmetic — only for narration.

This engine consumes the same time_series dict structure that existing
V1 agents use, ensuring backward compatibility.

Categories:
1. Revenue Intelligence       7. Efficiency Intelligence
2. Cost Intelligence          8. Return Intelligence
3. Profitability Intelligence 9. Cash Flow Intelligence
4. Liquidity Intelligence    10. Growth Intelligence
5. Solvency Intelligence     11. Trend Intelligence
6. Debt Servicing            12. Risk Intelligence
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

RiskStatus = Literal["PASS", "WARN", "FAIL"]
Trend = Literal["increasing", "declining", "stable"]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_series(ts: dict[str, Any], key: str) -> dict[str, float]:
    """Extract {period -> value} from the standard time_series format."""
    items = ts.get(key)
    if items is None:
        return {}
    if not isinstance(items, list):
        return {}

    out: dict[str, float] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        p = it.get("period")
        v = it.get("value")
        if not isinstance(p, str) or not p.strip() or v is None:
            continue
        try:
            vf = float(v)
        except (TypeError, ValueError):
            continue
        if np.isnan(vf):
            continue
        out[p.strip()] = vf
    return out


def _safe_div(a: float, b: float) -> float | None:
    """Safe division — returns None if denominator is zero or NaN."""
    if b == 0 or np.isnan(b) or np.isnan(a):
        return None
    return a / b


def _avg_yoy_growth(values: list[float]) -> float | None:
    """Average year-over-year growth in percent."""
    if len(values) < 2:
        return None
    growths = []
    for i in range(1, len(values)):
        if values[i - 1] != 0:
            growths.append((values[i] - values[i - 1]) / abs(values[i - 1]) * 100.0)
    if not growths:
        return None
    return float(np.mean(growths))


def _cagr(first: float, last: float, years: int) -> float | None:
    """Compound annual growth rate in percent."""
    if years < 1 or first <= 0 or last <= 0:
        return None
    return float(((last / first) ** (1.0 / years) - 1.0) * 100.0)


def _trend_direction(values: list[float]) -> Trend:
    """Classify trend using linear regression slope."""
    if len(values) < 2:
        return "stable"
    x = np.arange(len(values), dtype=float)
    y = np.array(values, dtype=float)
    slope = float(np.polyfit(x, y, deg=1)[0])
    mean_abs = float(np.mean(np.abs(y)))
    if mean_abs == 0:
        return "stable"
    norm = slope / mean_abs
    if norm > 0.01:
        return "increasing"
    if norm < -0.01:
        return "declining"
    return "stable"


def _risk_flag(value: float | None, warn_thresh: float, fail_thresh: float,
               higher_is_worse: bool = True) -> dict[str, Any]:
    """Generate a deterministic PASS/WARN/FAIL flag."""
    if value is None:
        return {"value": None, "status": "SKIP", "reason": "Insufficient data"}

    if higher_is_worse:
        if value >= fail_thresh:
            return {"value": round(value, 4), "status": "FAIL", "threshold": fail_thresh}
        if value >= warn_thresh:
            return {"value": round(value, 4), "status": "WARN", "threshold": warn_thresh}
        return {"value": round(value, 4), "status": "PASS"}
    else:
        # Lower is worse (e.g., current ratio)
        if value <= fail_thresh:
            return {"value": round(value, 4), "status": "FAIL", "threshold": fail_thresh}
        if value <= warn_thresh:
            return {"value": round(value, 4), "status": "WARN", "threshold": warn_thresh}
        return {"value": round(value, 4), "status": "PASS"}


# ─────────────────────────────────────────────────────────────────────────────
# Main Engine
# ─────────────────────────────────────────────────────────────────────────────


def compute_all_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute all 12 metric categories from a standard FinVeritas payload.

    Args:
        payload: The OCR/ingestion output dict with 'entity' and 'time_series'.

    Returns:
        Dict with keys for each category containing computed metrics.
        Missing data categories are flagged as 'unavailable' rather than
        raising exceptions — this is a key V2 improvement over V1.
    """
    entity = payload.get("entity", {})
    entity_id = str(entity.get("entity_id") or "UNKNOWN")

    ts = payload.get("time_series")
    if not isinstance(ts, dict):
        return {"error": "Missing or invalid 'time_series' in payload", "entity": entity_id}

    # ── Extract all available series ──────────────────────────────────────
    revenue_map = _extract_series(ts, "revenue")
    cogs_map = _extract_series(ts, "cost_of_goods_sold")
    sga_map = _extract_series(ts, "selling_general_admin")
    rnd_map = _extract_series(ts, "research_development")
    depreciation_map = _extract_series(ts, "depreciation_amortization")
    operating_income_map = _extract_series(ts, "operating_income")
    net_income_map = _extract_series(ts, "net_income")
    ebitda_map = _extract_series(ts, "ebitda")
    interest_expense_map = _extract_series(ts, "interest_expense")
    tax_map = _extract_series(ts, "income_tax")

    total_assets_map = _extract_series(ts, "total_assets")
    total_liabilities_map = _extract_series(ts, "total_liabilities")
    equity_map = _extract_series(ts, "equity")
    current_assets_map = _extract_series(ts, "current_assets")
    current_liabilities_map = _extract_series(ts, "current_liabilities")
    cash_map = _extract_series(ts, "cash_and_equivalents")
    inventory_map = _extract_series(ts, "inventory")
    receivables_map = _extract_series(ts, "accounts_receivable")
    payables_map = _extract_series(ts, "accounts_payable")
    total_debt_map = _extract_series(ts, "total_debt")

    ocf_map = _extract_series(ts, "operating_cash_flow")
    capex_map = _extract_series(ts, "capital_expenditures")

    shares_map = _extract_series(ts, "shares_outstanding")

    # ── Align periods ─────────────────────────────────────────────────────
    # Use revenue periods as the base timeline
    if not revenue_map:
        return {"error": "No revenue data available", "entity": entity_id}

    periods = sorted(revenue_map.keys())

    def _vals(m: dict[str, float]) -> list[float | None]:
        """Get values aligned to periods, None where missing."""
        return [m.get(p) for p in periods]

    rev_vals = _vals(revenue_map)

    result: dict[str, Any] = {
        "entity": entity_id,
        "periods": periods,
        "period_count": len(periods),
    }

    # ──────────────────────────────────────────────────────────────────────
    # 1. REVENUE INTELLIGENCE
    # ──────────────────────────────────────────────────────────────────────
    rev_clean = [v for v in rev_vals if v is not None]
    result["revenue_intelligence"] = {
        "available": len(rev_clean) >= 2,
        "total_revenue_latest": rev_clean[-1] if rev_clean else None,
        "yoy_growth_pct": _avg_yoy_growth(rev_clean) if len(rev_clean) >= 2 else None,
        "cagr_pct": _cagr(rev_clean[0], rev_clean[-1], len(rev_clean) - 1) if len(rev_clean) >= 2 else None,
        "trend": _trend_direction(rev_clean) if len(rev_clean) >= 2 else None,
        "volatility": float(pd.Series(rev_clean).pct_change().dropna().std() * 100) if len(rev_clean) >= 3 else None,
    }

    # ──────────────────────────────────────────────────────────────────────
    # 2. COST INTELLIGENCE
    # ──────────────────────────────────────────────────────────────────────
    cogs_vals = [cogs_map.get(p) for p in periods]
    sga_vals = [sga_map.get(p) for p in periods]
    rnd_vals = [rnd_map.get(p) for p in periods]
    depr_vals = [depreciation_map.get(p) for p in periods]

    has_cost = any(v is not None for v in cogs_vals)
    cost_metrics: dict[str, Any] = {"available": has_cost}

    if has_cost:
        # COGS to Revenue ratio (latest period where both exist)
        for i in range(len(periods) - 1, -1, -1):
            if cogs_vals[i] is not None and rev_vals[i] is not None and rev_vals[i] != 0:
                cost_metrics["cogs_to_revenue_pct"] = round(cogs_vals[i] / rev_vals[i] * 100, 2)
                break

        # SG&A ratio
        for i in range(len(periods) - 1, -1, -1):
            if sga_vals[i] is not None and rev_vals[i] is not None and rev_vals[i] != 0:
                cost_metrics["sga_to_revenue_pct"] = round(sga_vals[i] / rev_vals[i] * 100, 2)
                break

        # R&D ratio
        for i in range(len(periods) - 1, -1, -1):
            if rnd_vals[i] is not None and rev_vals[i] is not None and rev_vals[i] != 0:
                cost_metrics["rnd_to_revenue_pct"] = round(rnd_vals[i] / rev_vals[i] * 100, 2)
                break

        cogs_clean = [v for v in cogs_vals if v is not None]
        cost_metrics["cogs_trend"] = _trend_direction(cogs_clean) if len(cogs_clean) >= 2 else None

    result["cost_intelligence"] = cost_metrics

    # ──────────────────────────────────────────────────────────────────────
    # 3. PROFITABILITY INTELLIGENCE
    # ──────────────────────────────────────────────────────────────────────
    prof_metrics: dict[str, Any] = {"available": False}

    # Gross Margin
    gross_margins = []
    for i, p in enumerate(periods):
        r = rev_vals[i]
        c = cogs_vals[i] if i < len(cogs_vals) else None
        if r is not None and c is not None and r != 0:
            gross_margins.append({"period": p, "value": round((r - c) / r * 100, 2)})

    if gross_margins:
        prof_metrics["available"] = True
        prof_metrics["gross_margin_pct"] = gross_margins[-1]["value"]
        prof_metrics["gross_margin_trend"] = _trend_direction([gm["value"] for gm in gross_margins])

    # EBITDA Margin
    ebitda_margins = []
    for p in periods:
        e = ebitda_map.get(p)
        r = revenue_map.get(p)
        if e is not None and r is not None and r != 0:
            ebitda_margins.append({"period": p, "value": round(e / r * 100, 2)})

    if ebitda_margins:
        prof_metrics["available"] = True
        prof_metrics["ebitda_margin_pct"] = ebitda_margins[-1]["value"]
        prof_metrics["ebitda_margin_trend"] = _trend_direction([em["value"] for em in ebitda_margins])

    # Net Margin
    net_margins = []
    for p in periods:
        ni = net_income_map.get(p)
        r = revenue_map.get(p)
        if ni is not None and r is not None and r != 0:
            net_margins.append({"period": p, "value": round(ni / r * 100, 2)})

    if net_margins:
        prof_metrics["available"] = True
        prof_metrics["net_margin_pct"] = net_margins[-1]["value"]
        prof_metrics["net_margin_trend"] = _trend_direction([nm["value"] for nm in net_margins])

    # EPS
    eps_vals = []
    for p in periods:
        ni = net_income_map.get(p)
        sh = shares_map.get(p)
        if ni is not None and sh is not None and sh > 0:
            eps_vals.append({"period": p, "value": round(ni / sh, 2)})

    if eps_vals:
        prof_metrics["eps_latest"] = eps_vals[-1]["value"]
        prof_metrics["eps_trend"] = _trend_direction([e["value"] for e in eps_vals])

    result["profitability_intelligence"] = prof_metrics

    # ──────────────────────────────────────────────────────────────────────
    # 4. LIQUIDITY INTELLIGENCE
    # ──────────────────────────────────────────────────────────────────────
    liq_metrics: dict[str, Any] = {"available": False}

    current_ratios = []
    quick_ratios = []
    cash_ratios = []

    for p in periods:
        ca = current_assets_map.get(p)
        cl = current_liabilities_map.get(p)
        inv = inventory_map.get(p)
        cash = cash_map.get(p)

        if ca is not None and cl is not None and cl > 0:
            liq_metrics["available"] = True
            cr = ca / cl
            current_ratios.append({"period": p, "value": round(cr, 4)})

            # Quick ratio = (CA - Inventory) / CL
            if inv is not None:
                qr = (ca - inv) / cl
                quick_ratios.append({"period": p, "value": round(qr, 4)})

            # Cash ratio = Cash / CL
            if cash is not None:
                cashr = cash / cl
                cash_ratios.append({"period": p, "value": round(cashr, 4)})

    if current_ratios:
        liq_metrics["current_ratio_latest"] = current_ratios[-1]["value"]
        liq_metrics["current_ratio_avg"] = round(float(np.mean([cr["value"] for cr in current_ratios])), 4)
        liq_metrics["current_ratio_trend"] = _trend_direction([cr["value"] for cr in current_ratios])

    if quick_ratios:
        liq_metrics["quick_ratio_latest"] = quick_ratios[-1]["value"]

    if cash_ratios:
        liq_metrics["cash_ratio_latest"] = cash_ratios[-1]["value"]

    # Working capital
    wc_vals = []
    for p in periods:
        ca = current_assets_map.get(p)
        cl = current_liabilities_map.get(p)
        if ca is not None and cl is not None:
            wc_vals.append(ca - cl)
    if wc_vals:
        liq_metrics["working_capital_latest"] = round(wc_vals[-1], 2)
        liq_metrics["working_capital_trend"] = _trend_direction(wc_vals)

    result["liquidity_intelligence"] = liq_metrics

    # ──────────────────────────────────────────────────────────────────────
    # 5. SOLVENCY INTELLIGENCE
    # ──────────────────────────────────────────────────────────────────────
    solv_metrics: dict[str, Any] = {"available": False}

    de_ratios = []
    for p in periods:
        tl = total_liabilities_map.get(p)
        eq = equity_map.get(p)
        if tl is not None and eq is not None and eq != 0:
            solv_metrics["available"] = True
            de_ratios.append({"period": p, "value": round(tl / eq, 4)})

    if de_ratios:
        solv_metrics["debt_to_equity_latest"] = de_ratios[-1]["value"]
        solv_metrics["debt_to_equity_trend"] = _trend_direction([d["value"] for d in de_ratios])

    # Debt to Assets
    da_ratios = []
    for p in periods:
        tl = total_liabilities_map.get(p)
        ta = total_assets_map.get(p)
        if tl is not None and ta is not None and ta > 0:
            da_ratios.append({"period": p, "value": round(tl / ta, 4)})

    if da_ratios:
        solv_metrics["available"] = True
        solv_metrics["debt_to_assets_latest"] = da_ratios[-1]["value"]

    # Interest Coverage = EBIT / Interest Expense
    ic_vals = []
    for p in periods:
        oi = operating_income_map.get(p)
        ie = interest_expense_map.get(p)
        if oi is not None and ie is not None and ie > 0:
            ic_vals.append({"period": p, "value": round(oi / ie, 4)})

    if ic_vals:
        solv_metrics["available"] = True
        solv_metrics["interest_coverage_latest"] = ic_vals[-1]["value"]
        solv_metrics["interest_coverage_trend"] = _trend_direction([ic["value"] for ic in ic_vals])

    # Equity Ratio
    er_vals = []
    for p in periods:
        eq = equity_map.get(p)
        ta = total_assets_map.get(p)
        if eq is not None and ta is not None and ta > 0:
            er_vals.append(round(eq / ta, 4))
    if er_vals:
        solv_metrics["equity_ratio_latest"] = er_vals[-1]

    result["solvency_intelligence"] = solv_metrics

    # ──────────────────────────────────────────────────────────────────────
    # 6. DEBT SERVICING INTELLIGENCE
    # ──────────────────────────────────────────────────────────────────────
    debt_metrics: dict[str, Any] = {"available": False}

    # DSCR = Net Operating Income / Total Debt Service
    # Approximation: EBITDA / Interest Expense (when full debt schedule unavailable)
    dscr_vals = []
    for p in periods:
        ebitda = ebitda_map.get(p)
        ie = interest_expense_map.get(p)
        if ebitda is not None and ie is not None and ie > 0:
            debt_metrics["available"] = True
            dscr_vals.append({"period": p, "value": round(ebitda / ie, 4)})

    if dscr_vals:
        debt_metrics["dscr_estimated_latest"] = dscr_vals[-1]["value"]
        debt_metrics["dscr_estimated_trend"] = _trend_direction([d["value"] for d in dscr_vals])
        debt_metrics["dscr_note"] = "Estimated using EBITDA/Interest Expense (full debt schedule not available)"

    result["debt_servicing_intelligence"] = debt_metrics

    # ──────────────────────────────────────────────────────────────────────
    # 7. EFFICIENCY INTELLIGENCE
    # ──────────────────────────────────────────────────────────────────────
    eff_metrics: dict[str, Any] = {"available": False}

    # Asset Turnover = Revenue / Total Assets
    at_vals = []
    for p in periods:
        r = revenue_map.get(p)
        ta = total_assets_map.get(p)
        if r is not None and ta is not None and ta > 0:
            eff_metrics["available"] = True
            at_vals.append({"period": p, "value": round(r / ta, 4)})

    if at_vals:
        eff_metrics["asset_turnover_latest"] = at_vals[-1]["value"]
        eff_metrics["asset_turnover_trend"] = _trend_direction([a["value"] for a in at_vals])

    # Receivables Turnover & DSO
    rt_vals = []
    for p in periods:
        r = revenue_map.get(p)
        ar = receivables_map.get(p)
        if r is not None and ar is not None and ar > 0:
            eff_metrics["available"] = True
            turnover = r / ar
            dso = 365.0 / turnover
            rt_vals.append({"period": p, "turnover": round(turnover, 4), "dso": round(dso, 1)})

    if rt_vals:
        eff_metrics["receivables_turnover_latest"] = rt_vals[-1]["turnover"]
        eff_metrics["dso_latest"] = rt_vals[-1]["dso"]

    # Inventory Turnover & DIO
    it_vals = []
    for p in periods:
        c = cogs_map.get(p)
        inv = inventory_map.get(p)
        if c is not None and inv is not None and inv > 0:
            eff_metrics["available"] = True
            turnover = c / inv
            dio = 365.0 / turnover
            it_vals.append({"period": p, "turnover": round(turnover, 4), "dio": round(dio, 1)})

    if it_vals:
        eff_metrics["inventory_turnover_latest"] = it_vals[-1]["turnover"]
        eff_metrics["dio_latest"] = it_vals[-1]["dio"]

    # Payables Turnover & DPO
    pt_vals = []
    for p in periods:
        c = cogs_map.get(p)
        ap = payables_map.get(p)
        if c is not None and ap is not None and ap > 0:
            eff_metrics["available"] = True
            turnover = c / ap
            dpo = 365.0 / turnover
            pt_vals.append({"period": p, "turnover": round(turnover, 4), "dpo": round(dpo, 1)})

    if pt_vals:
        eff_metrics["payables_turnover_latest"] = pt_vals[-1]["turnover"]
        eff_metrics["dpo_latest"] = pt_vals[-1]["dpo"]

    # Cash Conversion Cycle = DSO + DIO - DPO
    if rt_vals and it_vals and pt_vals:
        latest_dso = rt_vals[-1]["dso"]
        latest_dio = it_vals[-1]["dio"]
        latest_dpo = pt_vals[-1]["dpo"]
        ccc = latest_dso + latest_dio - latest_dpo
        eff_metrics["cash_conversion_cycle_days"] = round(ccc, 1)

    result["efficiency_intelligence"] = eff_metrics

    # ──────────────────────────────────────────────────────────────────────
    # 8. RETURN INTELLIGENCE
    # ──────────────────────────────────────────────────────────────────────
    ret_metrics: dict[str, Any] = {"available": False}

    # ROE = Net Income / Equity
    roe_vals = []
    for p in periods:
        ni = net_income_map.get(p)
        eq = equity_map.get(p)
        if ni is not None and eq is not None and eq != 0:
            ret_metrics["available"] = True
            roe_vals.append({"period": p, "value": round(ni / eq * 100, 2)})

    if roe_vals:
        ret_metrics["roe_pct_latest"] = roe_vals[-1]["value"]
        ret_metrics["roe_trend"] = _trend_direction([r["value"] for r in roe_vals])

    # ROA = Net Income / Total Assets
    roa_vals = []
    for p in periods:
        ni = net_income_map.get(p)
        ta = total_assets_map.get(p)
        if ni is not None and ta is not None and ta > 0:
            ret_metrics["available"] = True
            roa_vals.append({"period": p, "value": round(ni / ta * 100, 2)})

    if roa_vals:
        ret_metrics["roa_pct_latest"] = roa_vals[-1]["value"]
        ret_metrics["roa_trend"] = _trend_direction([r["value"] for r in roa_vals])

    # ROCE = EBIT / (Total Assets - Current Liabilities)
    roce_vals = []
    for p in periods:
        oi = operating_income_map.get(p)
        ta = total_assets_map.get(p)
        cl = current_liabilities_map.get(p)
        if oi is not None and ta is not None and cl is not None:
            ce = ta - cl
            if ce > 0:
                ret_metrics["available"] = True
                roce_vals.append({"period": p, "value": round(oi / ce * 100, 2)})

    if roce_vals:
        ret_metrics["roce_pct_latest"] = roce_vals[-1]["value"]
        ret_metrics["roce_trend"] = _trend_direction([r["value"] for r in roce_vals])

    result["return_intelligence"] = ret_metrics

    # ──────────────────────────────────────────────────────────────────────
    # 9. CASH FLOW INTELLIGENCE
    # ──────────────────────────────────────────────────────────────────────
    cf_metrics: dict[str, Any] = {"available": False}

    ocf_vals_clean = []
    for p in periods:
        o = ocf_map.get(p)
        if o is not None:
            cf_metrics["available"] = True
            ocf_vals_clean.append({"period": p, "value": o})

    if ocf_vals_clean:
        cf_metrics["ocf_latest"] = round(ocf_vals_clean[-1]["value"], 2)
        cf_metrics["ocf_trend"] = _trend_direction([o["value"] for o in ocf_vals_clean])

    # FCF = OCF - CapEx
    fcf_vals = []
    for p in periods:
        o = ocf_map.get(p)
        c = capex_map.get(p)
        if o is not None and c is not None:
            # CapEx is typically negative in reports; take absolute
            fcf = o - abs(c)
            fcf_vals.append({"period": p, "value": round(fcf, 2)})

    if fcf_vals:
        cf_metrics["fcf_latest"] = fcf_vals[-1]["value"]
        cf_metrics["fcf_trend"] = _trend_direction([f["value"] for f in fcf_vals])

    # OCF to Revenue
    ocf_rev_ratios = []
    for p in periods:
        o = ocf_map.get(p)
        r = revenue_map.get(p)
        if o is not None and r is not None and r != 0:
            ocf_rev_ratios.append(round(o / r * 100, 2))
    if ocf_rev_ratios:
        cf_metrics["ocf_to_revenue_pct"] = ocf_rev_ratios[-1]

    result["cash_flow_intelligence"] = cf_metrics

    # ──────────────────────────────────────────────────────────────────────
    # 10. GROWTH INTELLIGENCE
    # ──────────────────────────────────────────────────────────────────────
    growth_metrics: dict[str, Any] = {"available": len(rev_clean) >= 2}

    if len(rev_clean) >= 2:
        growth_metrics["revenue_growth_pct"] = _avg_yoy_growth(rev_clean)
        growth_metrics["revenue_cagr_pct"] = _cagr(rev_clean[0], rev_clean[-1], len(rev_clean) - 1)

    ni_clean = [net_income_map.get(p) for p in periods if net_income_map.get(p) is not None]
    if len(ni_clean) >= 2:
        growth_metrics["available"] = True
        growth_metrics["net_income_growth_pct"] = _avg_yoy_growth(ni_clean)

    ta_clean = [total_assets_map.get(p) for p in periods if total_assets_map.get(p) is not None]
    if len(ta_clean) >= 2:
        growth_metrics["total_assets_growth_pct"] = _avg_yoy_growth(ta_clean)

    eq_clean = [equity_map.get(p) for p in periods if equity_map.get(p) is not None]
    if len(eq_clean) >= 2:
        growth_metrics["equity_growth_pct"] = _avg_yoy_growth(eq_clean)

    result["growth_intelligence"] = growth_metrics

    # ──────────────────────────────────────────────────────────────────────
    # 11. TREND INTELLIGENCE
    # ──────────────────────────────────────────────────────────────────────
    trend_metrics: dict[str, Any] = {"available": len(rev_clean) >= 2}

    if len(rev_clean) >= 2:
        trend_metrics["revenue_trend"] = _trend_direction(rev_clean)

    if len(ni_clean) >= 2:
        trend_metrics["available"] = True
        trend_metrics["net_income_trend"] = _trend_direction(ni_clean)

    if len(ta_clean) >= 2:
        trend_metrics["total_assets_trend"] = _trend_direction(ta_clean)

    if de_ratios:
        trend_metrics["leverage_trend"] = _trend_direction([d["value"] for d in de_ratios])

    result["trend_intelligence"] = trend_metrics

    # ──────────────────────────────────────────────────────────────────────
    # 12. RISK INTELLIGENCE (Deterministic PASS/WARN/FAIL)
    # ──────────────────────────────────────────────────────────────────────
    risk_flags: list[dict[str, Any]] = []

    # Current Ratio < 1.0 is risky, < 0.8 is critical
    if current_ratios:
        cr_val = current_ratios[-1]["value"]
        risk_flags.append({
            "metric": "Current Ratio",
            **_risk_flag(cr_val, warn_thresh=1.2, fail_thresh=0.8, higher_is_worse=False),
        })

    # Debt/Equity > 2.0 is concerning, > 3.0 is critical
    if de_ratios:
        de_val = de_ratios[-1]["value"]
        risk_flags.append({
            "metric": "Debt-to-Equity",
            **_risk_flag(de_val, warn_thresh=2.0, fail_thresh=3.0, higher_is_worse=True),
        })

    # Interest Coverage < 2.0 is concerning, < 1.0 is critical
    if ic_vals:
        ic_val = ic_vals[-1]["value"]
        risk_flags.append({
            "metric": "Interest Coverage",
            **_risk_flag(ic_val, warn_thresh=2.0, fail_thresh=1.0, higher_is_worse=False),
        })

    # Negative working capital
    if wc_vals:
        wc_flag = "PASS"
        if wc_vals[-1] < 0:
            wc_flag = "FAIL"
        elif len(wc_vals) >= 2 and wc_vals[-1] < wc_vals[-2]:
            wc_flag = "WARN"
        risk_flags.append({
            "metric": "Working Capital",
            "value": round(wc_vals[-1], 2),
            "status": wc_flag,
        })

    # Revenue declining
    if len(rev_clean) >= 2:
        rev_trend = _trend_direction(rev_clean)
        risk_flags.append({
            "metric": "Revenue Trend",
            "value": rev_trend,
            "status": "FAIL" if rev_trend == "declining" else "PASS",
        })

    # DSCR < 1.5 is warning, < 1.0 means cannot service debt
    if dscr_vals:
        dscr_val = dscr_vals[-1]["value"]
        risk_flags.append({
            "metric": "DSCR (Estimated)",
            **_risk_flag(dscr_val, warn_thresh=1.5, fail_thresh=1.0, higher_is_worse=False),
        })

    result["risk_intelligence"] = {
        "available": len(risk_flags) > 0,
        "flags": risk_flags,
        "summary": {
            "pass_count": sum(1 for f in risk_flags if f.get("status") == "PASS"),
            "warn_count": sum(1 for f in risk_flags if f.get("status") == "WARN"),
            "fail_count": sum(1 for f in risk_flags if f.get("status") == "FAIL"),
            "total_checks": len(risk_flags),
        },
    }

    # ── Availability Summary ─────────────────────────────────────────────
    result["_availability_summary"] = {
        cat: result[cat].get("available", False)
        for cat in [
            "revenue_intelligence", "cost_intelligence", "profitability_intelligence",
            "liquidity_intelligence", "solvency_intelligence", "debt_servicing_intelligence",
            "efficiency_intelligence", "return_intelligence", "cash_flow_intelligence",
            "growth_intelligence", "trend_intelligence", "risk_intelligence",
        ]
    }

    return result
