"""Anomaly Alert System (V2)

Deterministic anomaly detection based on the Fact Ledger.
Generates PASS/WARN/FAIL alerts with explanations.

This extends the existing data_verifier.py (Credibility Engine) by
adding ongoing structural financial monitoring — not just data quality.

All thresholds are deterministic and based on standard financial analysis
benchmarks. The LLM is NOT involved in any alert logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


AlertSeverity = Literal["INFO", "WARN", "CRITICAL"]


@dataclass(frozen=True)
class AnomalyAlert:
    """A single anomaly alert."""
    category: str
    metric: str
    severity: AlertSeverity
    message: str
    value: Any = None
    threshold: Any = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "category": self.category,
            "metric": self.metric,
            "severity": self.severity,
            "message": self.message,
        }
        if self.value is not None:
            d["value"] = self.value
        if self.threshold is not None:
            d["threshold"] = self.threshold
        return d


def run_anomaly_detection(fact_ledger: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic anomaly detection on a fact ledger.

    Args:
        fact_ledger: The immutable fact ledger from build_fact_ledger().

    Returns:
        Dict containing alerts, summary counts, and overall health status.
    """
    metrics = fact_ledger.get("metrics", {})
    alerts: list[AnomalyAlert] = []

    # ── Revenue Anomalies ─────────────────────────────────────────────────
    rev = metrics.get("revenue_intelligence", {})
    if rev.get("available"):
        # Declining revenue
        if rev.get("trend") == "declining":
            alerts.append(AnomalyAlert(
                category="Revenue",
                metric="Revenue Trend",
                severity="CRITICAL",
                message="Revenue is on a declining trajectory. Investigate core business performance.",
                value=rev.get("trend"),
            ))

        # High volatility
        vol = rev.get("volatility")
        if vol is not None and vol > 25:
            alerts.append(AnomalyAlert(
                category="Revenue",
                metric="Revenue Volatility",
                severity="WARN",
                message=f"Revenue volatility is {vol:.1f}% — high instability in revenue stream.",
                value=round(vol, 2),
                threshold=25.0,
            ))

        # Negative CAGR
        cagr = rev.get("cagr_pct")
        if cagr is not None and cagr < 0:
            alerts.append(AnomalyAlert(
                category="Revenue",
                metric="Revenue CAGR",
                severity="CRITICAL",
                message=f"Revenue CAGR is {cagr:.1f}% — compound shrinkage over the analysis period.",
                value=round(cagr, 2),
            ))

    # ── Profitability Anomalies ───────────────────────────────────────────
    prof = metrics.get("profitability_intelligence", {})
    if prof.get("available"):
        net_margin = prof.get("net_margin_pct")
        if net_margin is not None and net_margin < 0:
            alerts.append(AnomalyAlert(
                category="Profitability",
                metric="Net Margin",
                severity="CRITICAL",
                message=f"Net margin is {net_margin:.1f}% — the company is generating losses.",
                value=round(net_margin, 2),
            ))

        gross_margin = prof.get("gross_margin_pct")
        if gross_margin is not None and gross_margin < 20:
            alerts.append(AnomalyAlert(
                category="Profitability",
                metric="Gross Margin",
                severity="WARN",
                message=f"Gross margin is {gross_margin:.1f}% — thin margins increase vulnerability.",
                value=round(gross_margin, 2),
                threshold=20.0,
            ))

        if prof.get("gross_margin_trend") == "declining":
            alerts.append(AnomalyAlert(
                category="Profitability",
                metric="Gross Margin Trend",
                severity="WARN",
                message="Gross margin is declining — cost pressures or pricing erosion may be occurring.",
            ))

    # ── Liquidity Anomalies ───────────────────────────────────────────────
    liq = metrics.get("liquidity_intelligence", {})
    if liq.get("available"):
        cr = liq.get("current_ratio_latest")
        if cr is not None:
            if cr < 1.0:
                alerts.append(AnomalyAlert(
                    category="Liquidity",
                    metric="Current Ratio",
                    severity="CRITICAL",
                    message=f"Current ratio is {cr:.2f} — short-term liabilities exceed current assets.",
                    value=round(cr, 4),
                    threshold=1.0,
                ))
            elif cr < 1.2:
                alerts.append(AnomalyAlert(
                    category="Liquidity",
                    metric="Current Ratio",
                    severity="WARN",
                    message=f"Current ratio is {cr:.2f} — approaching liquidity stress.",
                    value=round(cr, 4),
                    threshold=1.2,
                ))

        wc = liq.get("working_capital_latest")
        if wc is not None and wc < 0:
            alerts.append(AnomalyAlert(
                category="Liquidity",
                metric="Working Capital",
                severity="CRITICAL",
                message="Working capital is negative — potential inability to meet short-term obligations.",
                value=round(wc, 2),
            ))

    # ── Solvency Anomalies ────────────────────────────────────────────────
    solv = metrics.get("solvency_intelligence", {})
    if solv.get("available"):
        de = solv.get("debt_to_equity_latest")
        if de is not None:
            if de > 3.0:
                alerts.append(AnomalyAlert(
                    category="Solvency",
                    metric="Debt-to-Equity",
                    severity="CRITICAL",
                    message=f"D/E ratio is {de:.2f} — extreme leverage posing structural risk.",
                    value=round(de, 4),
                    threshold=3.0,
                ))
            elif de > 2.0:
                alerts.append(AnomalyAlert(
                    category="Solvency",
                    metric="Debt-to-Equity",
                    severity="WARN",
                    message=f"D/E ratio is {de:.2f} — elevated leverage.",
                    value=round(de, 4),
                    threshold=2.0,
                ))

        ic = solv.get("interest_coverage_latest")
        if ic is not None and ic < 1.5:
            alerts.append(AnomalyAlert(
                category="Solvency",
                metric="Interest Coverage",
                severity="CRITICAL",
                message=f"Interest coverage is {ic:.2f}x — company may struggle to service debt.",
                value=round(ic, 4),
                threshold=1.5,
            ))

    # ── Debt Servicing Anomalies ──────────────────────────────────────────
    debt = metrics.get("debt_servicing_intelligence", {})
    if debt.get("available"):
        dscr = debt.get("dscr_estimated_latest")
        if dscr is not None and dscr < 1.0:
            alerts.append(AnomalyAlert(
                category="Debt Servicing",
                metric="DSCR (Estimated)",
                severity="CRITICAL",
                message=f"Estimated DSCR is {dscr:.2f} — insufficient cash flow to service debt.",
                value=round(dscr, 4),
                threshold=1.0,
            ))

    # ── Efficiency Anomalies ──────────────────────────────────────────────
    eff = metrics.get("efficiency_intelligence", {})
    if eff.get("available"):
        ccc = eff.get("cash_conversion_cycle_days")
        if ccc is not None and ccc > 120:
            alerts.append(AnomalyAlert(
                category="Efficiency",
                metric="Cash Conversion Cycle",
                severity="WARN",
                message=f"CCC is {ccc:.0f} days — capital is locked for extended periods.",
                value=round(ccc, 1),
                threshold=120,
            ))

        dso = eff.get("dso_latest")
        if dso is not None and dso > 90:
            alerts.append(AnomalyAlert(
                category="Efficiency",
                metric="Days Sales Outstanding",
                severity="WARN",
                message=f"DSO is {dso:.0f} days — potential collection issues.",
                value=round(dso, 1),
                threshold=90,
            ))

    # ── Return Anomalies ──────────────────────────────────────────────────
    ret = metrics.get("return_intelligence", {})
    if ret.get("available"):
        roe = ret.get("roe_pct_latest")
        if roe is not None and roe < 0:
            alerts.append(AnomalyAlert(
                category="Returns",
                metric="ROE",
                severity="CRITICAL",
                message=f"ROE is {roe:.1f}% — negative return on equity.",
                value=round(roe, 2),
            ))

        roa = ret.get("roa_pct_latest")
        if roa is not None and roa < 0:
            alerts.append(AnomalyAlert(
                category="Returns",
                metric="ROA",
                severity="WARN",
                message=f"ROA is {roa:.1f}% — assets are not generating positive returns.",
                value=round(roa, 2),
            ))

    # ── Cash Flow Anomalies ───────────────────────────────────────────────
    cf = metrics.get("cash_flow_intelligence", {})
    if cf.get("available"):
        ocf = cf.get("ocf_latest")
        if ocf is not None and ocf < 0:
            alerts.append(AnomalyAlert(
                category="Cash Flow",
                metric="Operating Cash Flow",
                severity="CRITICAL",
                message="Negative operating cash flow — core operations are cash-burning.",
                value=round(ocf, 2),
            ))

        fcf = cf.get("fcf_latest")
        if fcf is not None and fcf < 0:
            alerts.append(AnomalyAlert(
                category="Cash Flow",
                metric="Free Cash Flow",
                severity="WARN",
                message="Negative free cash flow — company needs external financing for growth.",
                value=round(fcf, 2),
            ))

    # ── Build result ──────────────────────────────────────────────────────
    critical_count = sum(1 for a in alerts if a.severity == "CRITICAL")
    warn_count = sum(1 for a in alerts if a.severity == "WARN")
    info_count = sum(1 for a in alerts if a.severity == "INFO")

    if critical_count > 0:
        health = "AT RISK"
    elif warn_count > 2:
        health = "CAUTION"
    elif warn_count > 0:
        health = "MONITORING"
    else:
        health = "HEALTHY"

    return {
        "alerts": [a.to_dict() for a in alerts],
        "summary": {
            "critical": critical_count,
            "warnings": warn_count,
            "info": info_count,
            "total": len(alerts),
            "health_status": health,
        },
    }
