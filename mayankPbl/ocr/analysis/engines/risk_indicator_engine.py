"""Risk Indicator Engine

Consolidates deterministic risk signals from all financial calculators
into a unified risk dashboard. Each indicator is classified as:

  PASS — no concern
  WARN — elevated risk, warrants attention
  FAIL — critical risk, material concern for credit

The risk classification itself is ALWAYS deterministic. The LLM may
explain the result but must not change the classification.

Categories:
  - profitability: margin compression, operating losses
  - liquidity: current ratio, working capital
  - solvency: leverage, interest coverage
  - growth: revenue decline, negative trends
  - debt_service: DSCR adequacy
  - saas: Rule of 40, gross margin
"""
from __future__ import annotations

from typing import List, Optional

from shared.schema import (
    CheckStatus,
    DSCRResult,
    FactLedgerEntry,
    NormalizedCompanyRecord,
    RiskDashboard,
    RiskIndicator,
    RiskLevel,
)


def _indicator(
    name: str,
    category: str,
    status: CheckStatus,
    value: Optional[float] = None,
    threshold: Optional[str] = None,
    detail: str = "",
    weight: float = 1.0,
) -> RiskIndicator:
    return RiskIndicator(
        name=name,
        category=category,
        status=status,
        value=value,
        threshold=threshold,
        detail=detail,
        severity_weight=weight,
    )


def build_risk_dashboard(
    record: NormalizedCompanyRecord,
    fact_entries: List[FactLedgerEntry],
    dscr_result: Optional[DSCRResult] = None,
) -> RiskDashboard:
    """Build a consolidated risk dashboard from computed facts and DSCR.

    Collects all risk signals from the fact ledger entries (which already
    have risk_signal set by individual calculators) and adds supplementary
    structural risk checks.
    """
    indicators: List[RiskIndicator] = []

    # ── Collect risk signals from fact ledger entries ──────────────────────
    for entry in fact_entries:
        if entry.risk_signal is not None:
            indicators.append(_indicator(
                name=entry.display_name,
                category=entry.category,
                status=entry.risk_signal,
                value=entry.value,
                detail=entry.risk_detail or "",
                weight=1.0,
            ))

    # ── DSCR-specific risk ────────────────────────────────────────────────
    if dscr_result is not None:
        if dscr_result.dscr_ratio is not None:
            dscr_status = {
                RiskLevel.LOW: CheckStatus.PASS,
                RiskLevel.MODERATE: CheckStatus.PASS,
                RiskLevel.HIGH: CheckStatus.WARN,
                RiskLevel.CRITICAL: CheckStatus.FAIL,
            }.get(dscr_result.risk_level, CheckStatus.WARN)

            indicators.append(_indicator(
                name="Debt Service Coverage Ratio (DSCR)",
                category="debt_service",
                status=dscr_status,
                value=dscr_result.dscr_ratio,
                threshold="PASS ≥ 2.0 | WARN ≥ 1.0 | FAIL < 1.0",
                detail=dscr_result.interpretation or "",
                weight=2.0,  # Higher weight — directly relevant to lending
            ))

    # ── Supplementary structural checks ───────────────────────────────────

    # Check: Negative EBITDA
    latest_ebitda = record.latest_value("ebitda")
    if latest_ebitda is not None and latest_ebitda < 0:
        indicators.append(_indicator(
            name="Negative EBITDA",
            category="profitability",
            status=CheckStatus.FAIL,
            value=latest_ebitda,
            detail="EBITDA is negative — company is not generating operational cash flow",
            weight=2.0,
        ))

    # Check: Declining Revenue
    rev_sorted = sorted(record.revenue, key=lambda x: x.period) if record.revenue else []
    if len(rev_sorted) >= 2:
        latest_rev = rev_sorted[-1].value
        prev_rev = rev_sorted[-2].value
        if prev_rev > 0:
            rev_change_pct = ((latest_rev - prev_rev) / prev_rev) * 100
            if rev_change_pct < -10:
                indicators.append(_indicator(
                    name="Revenue Decline",
                    category="growth",
                    status=CheckStatus.FAIL,
                    value=round(rev_change_pct, 2),
                    threshold="FAIL < -10%",
                    detail=f"Revenue declined {rev_change_pct:.1f}% YoY — significant concern for debt serviceability",
                    weight=1.5,
                ))
            elif rev_change_pct < 0:
                indicators.append(_indicator(
                    name="Revenue Decline",
                    category="growth",
                    status=CheckStatus.WARN,
                    value=round(rev_change_pct, 2),
                    threshold="WARN < 0%",
                    detail=f"Revenue declined {rev_change_pct:.1f}% YoY — monitor closely",
                    weight=1.0,
                ))

    # Check: Negative Equity (Stockholders' Deficit)
    latest_eq = record.latest_value("equity")
    if latest_eq is not None and latest_eq < 0:
        indicators.append(_indicator(
            name="Negative Equity (Stockholders' Deficit)",
            category="solvency",
            status=CheckStatus.FAIL,
            value=latest_eq,
            detail="Negative equity indicates liabilities exceed assets — extreme leverage risk",
            weight=2.0,
        ))

    # Check: Negative Net Income (consecutive)
    ni_sorted = sorted(record.net_income, key=lambda x: x.period) if record.net_income else []
    if len(ni_sorted) >= 2:
        consecutive_losses = all(fp.value < 0 for fp in ni_sorted[-2:])
        if consecutive_losses:
            indicators.append(_indicator(
                name="Consecutive Net Losses",
                category="profitability",
                status=CheckStatus.WARN,
                detail="Company has reported net losses in the last 2 consecutive periods",
                weight=1.5,
            ))

    # Check: Working Capital (Current Assets - Current Liabilities)
    latest_ca = record.latest_value("current_assets")
    latest_cl = record.latest_value("current_liabilities")
    if latest_ca is not None and latest_cl is not None:
        wc = latest_ca - latest_cl
        if wc < 0:
            indicators.append(_indicator(
                name="Negative Working Capital",
                category="liquidity",
                status=CheckStatus.WARN,
                value=wc,
                detail="Current liabilities exceed current assets — potential short-term liquidity stress",
                weight=1.0,
            ))

    # ── Compute overall risk level ────────────────────────────────────────
    overall = _compute_overall_risk(indicators)

    return RiskDashboard(
        entity_id=record.entity_id,
        indicators=indicators,
        overall_risk=overall,
    )


def _compute_overall_risk(indicators: List[RiskIndicator]) -> RiskLevel:
    """Compute an overall risk level from individual indicators.

    Weighted scoring: FAIL = -weight, WARN = -0.5*weight, PASS = 0
    Then map total score to risk levels.
    """
    if not indicators:
        return RiskLevel.MODERATE  # No data = moderate by default

    total_weight = sum(i.severity_weight for i in indicators)
    if total_weight == 0:
        return RiskLevel.MODERATE

    # Count weighted failures and warnings
    fail_score = sum(i.severity_weight for i in indicators if i.status == CheckStatus.FAIL)
    warn_score = sum(i.severity_weight * 0.5 for i in indicators if i.status == CheckStatus.WARN)
    risk_score = (fail_score + warn_score) / total_weight

    if risk_score > 0.4:
        return RiskLevel.CRITICAL
    if risk_score > 0.25:
        return RiskLevel.HIGH
    if risk_score > 0.1:
        return RiskLevel.MODERATE
    return RiskLevel.LOW
