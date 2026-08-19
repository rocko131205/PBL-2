"""SaaS Metrics Engine — V2

V2 REPLACEMENT: The V1 engine used `profit_margin = 10.0` (hardcoded).
This module computes SaaS-relevant metrics using ACTUAL financial data.

Only metrics that genuinely improve credit/lending analysis are included.
Each metric is accompanied by a justification for why it matters for credit.

Metrics:
  - Revenue Growth Rate: Indicates cash flow trajectory
  - Gross Margin: SaaS typically >70%; lower suggests issues
  - Operating Margin (actual): Direct input to DSCR numerator
  - Rule of 40 (actual): Industry benchmark for business health
  - Revenue Stability: Low volatility = predictable cash flow
  - SaaS Classification: Whether company exhibits SaaS characteristics

Design constraints:
  - All computations are deterministic Python.
  - Never fabricate values — explicitly state when data is insufficient.
  - Every metric includes credit-analysis justification.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schema import (
    CheckStatus,
    FactLedgerEntry,
    FactStatus,
    NormalizedCompanyRecord,
)


def _safe_pct(numerator: float, denominator: float) -> Optional[float]:
    if abs(denominator) < 1e-9:
        return None
    return (numerator / denominator) * 100.0


def _compute_yoy_growth(values: List[float]) -> Optional[float]:
    """Compute most recent YoY growth rate (%)."""
    if len(values) < 2:
        return None
    prev, curr = values[-2], values[-1]
    if abs(prev) < 1e-9:
        return None
    return ((curr - prev) / abs(prev)) * 100.0


def _compute_cagr(values: List[float], n_periods: int) -> Optional[float]:
    """Compute CAGR over n_periods (%)."""
    if len(values) < 2 or n_periods < 1:
        return None
    first, last = values[0], values[-1]
    if first <= 0 or last <= 0:
        return None
    return ((last / first) ** (1.0 / n_periods) - 1.0) * 100.0


def _revenue_volatility(values: List[float]) -> Optional[float]:
    """Compute coefficient of variation of revenue (lower = more stable)."""
    if len(values) < 3:
        return None
    import numpy as np
    arr = np.array(values, dtype=float)
    mean = np.mean(arr)
    if abs(mean) < 1e-9:
        return None
    return float(np.std(arr, ddof=0) / abs(mean)) * 100.0  # percentage CV


def compute_saas_metrics(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    """Compute SaaS-relevant metrics using actual financial data.

    Returns FactLedgerEntry objects with credit-analysis justification.
    """
    entries: List[FactLedgerEntry] = []

    # Extract revenue time series (sorted by period)
    rev_sorted = sorted(record.revenue, key=lambda x: x.period) if record.revenue else []
    rev_values = [fp.value for fp in rev_sorted]

    latest_rev = record.latest_value("revenue")
    latest_gp = record.latest_value("gross_profit")
    latest_oi = record.latest_value("operating_income")
    latest_cogs = record.latest_value("cost_of_revenue")

    # Determine period
    period = rev_sorted[-1].period if rev_sorted else None

    # ── Revenue Growth Rate ───────────────────────────────────────────────
    yoy_growth = _compute_yoy_growth(rev_values) if len(rev_values) >= 2 else None
    if yoy_growth is not None:
        entries.append(FactLedgerEntry(
            metric="saas_revenue_growth",
            display_name="Revenue Growth Rate (YoY)",
            category="saas",
            value=round(yoy_growth, 2),
            unit="%",
            period=period,
            formula="(Revenue_T - Revenue_T-1) / Revenue_T-1 × 100",
            inputs_used=["revenue"],
            status=FactStatus.VALID,
            notes="Credit relevance: Indicates future cash flow trajectory; fast growth may offset current leverage",
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="saas_revenue_growth",
            display_name="Revenue Growth Rate (YoY)",
            category="saas",
            value=None,
            unit="%",
            formula="(Revenue_T - Revenue_T-1) / Revenue_T-1 × 100",
            inputs_used=["revenue"],
            status=FactStatus.INSUFFICIENT_DATA,
            notes="Requires at least 2 periods of revenue data",
        ))

    # ── Revenue CAGR (3-year if available) ────────────────────────────────
    if len(rev_values) >= 4:
        cagr_3yr = _compute_cagr(rev_values[-4:], 3)
        if cagr_3yr is not None:
            entries.append(FactLedgerEntry(
                metric="saas_revenue_cagr_3yr",
                display_name="Revenue CAGR (3-Year)",
                category="saas",
                value=round(cagr_3yr, 2),
                unit="%",
                period=f"{rev_sorted[-4].period} → {period}",
                formula="((Revenue_T / Revenue_T-3)^(1/3) - 1) × 100",
                inputs_used=["revenue"],
                status=FactStatus.VALID,
                notes="Credit relevance: Multi-year growth trend is a stronger signal than single-year growth",
            ))

    # ── Gross Margin ──────────────────────────────────────────────────────
    gross_margin = None
    gm_method = "gross_profit"

    if latest_gp is not None and latest_rev is not None:
        gross_margin = _safe_pct(latest_gp, latest_rev)
    elif latest_cogs is not None and latest_rev is not None:
        # Reconstruct gross profit from revenue - COGS
        gp_reconstructed = latest_rev - latest_cogs
        gross_margin = _safe_pct(gp_reconstructed, latest_rev)
        gm_method = "revenue_minus_cogs"

    if gross_margin is not None:
        risk = None
        risk_detail = None
        if gross_margin >= 70:
            risk, risk_detail = CheckStatus.PASS, f"Gross margin {gross_margin:.1f}% — typical of healthy SaaS business"
        elif gross_margin >= 50:
            risk, risk_detail = CheckStatus.PASS, f"Gross margin {gross_margin:.1f}% — acceptable but below SaaS average"
        elif gross_margin >= 30:
            risk, risk_detail = CheckStatus.WARN, f"Gross margin {gross_margin:.1f}% — low for SaaS; may indicate significant infrastructure or delivery costs"
        else:
            risk, risk_detail = CheckStatus.WARN, f"Gross margin {gross_margin:.1f}% — atypically low for SaaS; investigate revenue composition"

        formula = "Gross Profit / Revenue × 100" if gm_method == "gross_profit" else "(Revenue − COGS) / Revenue × 100"
        entries.append(FactLedgerEntry(
            metric="saas_gross_margin",
            display_name="Gross Margin (SaaS Context)",
            category="saas",
            value=round(gross_margin, 2),
            unit="%",
            period=period,
            formula=formula,
            inputs_used=["gross_profit", "revenue"] if gm_method == "gross_profit" else ["cost_of_revenue", "revenue"],
            status=FactStatus.VALID,
            risk_signal=risk,
            risk_detail=risk_detail,
            notes="Credit relevance: SaaS companies typically have >70% gross margins; lower margins suggest non-SaaS revenue streams or high delivery costs, both relevant for credit assessment",
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="saas_gross_margin",
            display_name="Gross Margin (SaaS Context)",
            category="saas",
            value=None,
            unit="%",
            formula="Gross Profit / Revenue × 100",
            inputs_used=["gross_profit", "revenue"],
            status=FactStatus.INSUFFICIENT_DATA,
            notes="Requires gross_profit (or cost_of_revenue) and revenue data",
        ))

    # ── Operating Margin (actual, NOT hardcoded) ──────────────────────────
    operating_margin = None
    if latest_oi is not None and latest_rev is not None:
        operating_margin = _safe_pct(latest_oi, latest_rev)

    if operating_margin is not None:
        entries.append(FactLedgerEntry(
            metric="saas_operating_margin",
            display_name="Operating Margin (SaaS Context)",
            category="saas",
            value=round(operating_margin, 2),
            unit="%",
            period=period,
            formula="Operating Income / Revenue × 100",
            inputs_used=["operating_income", "revenue"],
            status=FactStatus.VALID,
            notes="Credit relevance: Direct proxy for cash generation capacity and DSCR numerator quality",
        ))

    # ── Rule of 40 (using ACTUAL data) ────────────────────────────────────
    if yoy_growth is not None and operating_margin is not None:
        rule_of_40 = yoy_growth + operating_margin
        risk = None
        risk_detail = None
        if rule_of_40 >= 40:
            risk, risk_detail = CheckStatus.PASS, f"Rule of 40 = {rule_of_40:.1f} — business is balancing growth and profitability effectively"
        elif rule_of_40 >= 25:
            risk, risk_detail = CheckStatus.PASS, f"Rule of 40 = {rule_of_40:.1f} — acceptable but below the 40 threshold"
        elif rule_of_40 >= 10:
            risk, risk_detail = CheckStatus.WARN, f"Rule of 40 = {rule_of_40:.1f} — company is neither growing fast nor profitable"
        else:
            risk, risk_detail = CheckStatus.FAIL, f"Rule of 40 = {rule_of_40:.1f} — significant concern: poor growth-profitability balance"

        entries.append(FactLedgerEntry(
            metric="saas_rule_of_40",
            display_name="Rule of 40",
            category="saas",
            value=round(rule_of_40, 2),
            unit="points",
            period=period,
            formula="Revenue Growth Rate (%) + Operating Margin (%)",
            inputs_used=["revenue", "operating_income"],
            status=FactStatus.VALID,
            risk_signal=risk,
            risk_detail=risk_detail,
            notes="Credit relevance: Industry benchmark — a SaaS company above 40 is generally considered financially healthy. Below 40 suggests the company may struggle to balance growth investment with profitability.",
        ))
    elif yoy_growth is not None and gross_margin is not None:
        # Fallback: use gross margin proxy (clearly labeled as estimated)
        rule_of_40_est = yoy_growth + gross_margin
        entries.append(FactLedgerEntry(
            metric="saas_rule_of_40",
            display_name="Rule of 40 (Estimated — Gross Margin Proxy)",
            category="saas",
            value=round(rule_of_40_est, 2),
            unit="points",
            period=period,
            formula="Revenue Growth Rate (%) + Gross Margin (%) [proxy — operating margin unavailable]",
            inputs_used=["revenue", "gross_profit"],
            status=FactStatus.ESTIMATED,
            notes="Operating margin unavailable — gross margin used as proxy. Rule of 40 with gross margin will be significantly higher than with operating margin. Interpret with caution.",
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="saas_rule_of_40",
            display_name="Rule of 40",
            category="saas",
            value=None,
            unit="points",
            formula="Revenue Growth Rate (%) + Operating Margin (%)",
            inputs_used=["revenue", "operating_income"],
            status=FactStatus.INSUFFICIENT_DATA,
            notes="Requires revenue growth (≥2 periods) and operating margin",
        ))

    # ── Revenue Stability ─────────────────────────────────────────────────
    if len(rev_values) >= 3:
        cv = _revenue_volatility(rev_values)
        if cv is not None:
            risk = None
            risk_detail = None
            if cv < 15:
                risk, risk_detail = CheckStatus.PASS, f"Revenue CV {cv:.1f}% — very stable/predictable"
            elif cv < 30:
                risk, risk_detail = CheckStatus.PASS, f"Revenue CV {cv:.1f}% — moderate stability"
            else:
                risk, risk_detail = CheckStatus.WARN, f"Revenue CV {cv:.1f}% — volatile revenue stream"

            entries.append(FactLedgerEntry(
                metric="saas_revenue_stability",
                display_name="Revenue Stability (CV)",
                category="saas",
                value=round(cv, 2),
                unit="%",
                period=f"{rev_sorted[0].period} → {period}",
                formula="StdDev(Revenue) / Mean(Revenue) × 100 (lower = more stable)",
                inputs_used=["revenue"],
                status=FactStatus.VALID,
                risk_signal=risk,
                risk_detail=risk_detail,
                notes="Credit relevance: SaaS subscription revenue should be predictable. High volatility suggests project-based or transactional revenue, which is riskier for lending.",
            ))

    # ── SaaS Characteristics Assessment ───────────────────────────────────
    saas_signals: List[str] = []
    non_saas_signals: List[str] = []

    if gross_margin is not None:
        if gross_margin >= 60:
            saas_signals.append(f"High gross margin ({gross_margin:.0f}%) typical of software delivery")
        else:
            non_saas_signals.append(f"Low gross margin ({gross_margin:.0f}%) suggests hardware/services component")

    if cv is not None if len(rev_values) >= 3 else False:
        if cv < 20:
            saas_signals.append("Stable revenue stream suggests recurring/subscription model")
        else:
            non_saas_signals.append("Volatile revenue may indicate non-recurring sales")

    if yoy_growth is not None and yoy_growth > 20:
        saas_signals.append(f"High growth rate ({yoy_growth:.0f}%) common in SaaS companies")

    classification = "unknown"
    if len(saas_signals) >= 2:
        classification = "likely_saas"
    elif len(saas_signals) >= 1 and len(non_saas_signals) == 0:
        classification = "possible_saas"
    elif len(non_saas_signals) >= 2:
        classification = "unlikely_saas"

    detail_parts = []
    if saas_signals:
        detail_parts.append("SaaS indicators: " + "; ".join(saas_signals))
    if non_saas_signals:
        detail_parts.append("Non-SaaS indicators: " + "; ".join(non_saas_signals))

    entries.append(FactLedgerEntry(
        metric="saas_classification",
        display_name="SaaS Business Characteristics",
        category="saas",
        value=None,
        unit="classification",
        formula="Deterministic assessment based on gross margin, revenue stability, and growth pattern",
        inputs_used=["gross_profit", "revenue", "operating_income"],
        status=FactStatus.VALID,
        notes=f"Classification: {classification}. {' '.join(detail_parts)}",
    ))

    return entries
