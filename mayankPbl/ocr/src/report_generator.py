"""Report Generator — Lender-Facing Credit Assessment Report

Transforms a CreditAssessmentReport into a structured, lender-facing document.
Includes DSCR with full methodology, financial metrics summary, peer comparison,
qualitative findings, risk dashboard, data quality notes, and recommendation.

Output formats:
  - Structured dict for UI rendering
  - JSON export for downstream consumption
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schema import (
    CheckStatus,
    CreditAssessmentReport,
    DSCRResult,
    FactLedgerEntry,
    FactStatus,
    FinancialFactLedger,
    PeerComparison,
    RiskDashboard,
    RiskLevel,
)


def _risk_color(level: RiskLevel) -> str:
    return {
        RiskLevel.LOW: "#00FF88",
        RiskLevel.MODERATE: "#FFB000",
        RiskLevel.HIGH: "#FF6B35",
        RiskLevel.CRITICAL: "#FF3333",
        RiskLevel.INSUFFICIENT_DATA: "#888888",
    }.get(level, "#888888")


def _check_color(status: CheckStatus) -> str:
    return {
        CheckStatus.PASS: "#00FF88",
        CheckStatus.WARN: "#FFB000",
        CheckStatus.FAIL: "#FF3333",
        CheckStatus.SKIP: "#888888",
    }.get(status, "#888888")


def generate_report_sections(
    report: CreditAssessmentReport,
    fact_ledger: Optional[FinancialFactLedger] = None,
) -> Dict[str, Any]:
    """Generate structured report sections for UI rendering.

    Returns a dict with sections that the frontend can render:
      - executive_summary
      - dscr_section
      - financial_metrics (by category)
      - peer_comparison
      - risk_indicators
      - qualitative_findings
      - methodology_notes
      - recommendations
    """
    sections: Dict[str, Any] = {}

    # ── Executive Summary ─────────────────────────────────────────────────
    sections["executive_summary"] = {
        "entity": report.entity_id,
        "analysis_date": report.analysis_date,
        "currency": report.currency or "N/A",
        "overall_risk": report.risk_classification.value,
        "risk_color": _risk_color(report.risk_classification),
        "saas_classification": report.saas_classification or "Not classified",
        "disclaimer": report.disclaimer,
    }

    # ── DSCR Section ──────────────────────────────────────────────────────
    if report.dscr_result:
        dscr = report.dscr_result
        sections["dscr"] = {
            "ratio": dscr.dscr_ratio,
            "risk_level": dscr.risk_level.value,
            "risk_color": _risk_color(dscr.risk_level),
            "numerator": dscr.numerator_value,
            "denominator": dscr.denominator_value,
            "methodology": {
                "numerator_name": dscr.methodology.numerator_name,
                "numerator_formula": dscr.methodology.numerator_formula,
                "numerator_source": dscr.methodology.numerator_source,
                "denominator_components": dscr.methodology.denominator_components,
                "time_period": dscr.methodology.time_period,
                "assumptions": dscr.methodology.assumptions,
                "limitations": dscr.methodology.limitations,
            },
            "interpretation": dscr.interpretation,
        }
    else:
        sections["dscr"] = None

    # ── Financial Metrics by Category ─────────────────────────────────────
    metrics_by_category: Dict[str, List[Dict[str, Any]]] = {}
    if fact_ledger:
        for entry in fact_ledger.entries:
            cat = entry.category
            if cat not in metrics_by_category:
                metrics_by_category[cat] = []
            metrics_by_category[cat].append({
                "metric": entry.metric,
                "display_name": entry.display_name,
                "value": entry.value,
                "unit": entry.unit,
                "period": entry.period,
                "formula": entry.formula,
                "status": entry.status.value,
                "risk_signal": entry.risk_signal.value if entry.risk_signal else None,
                "risk_color": _check_color(entry.risk_signal) if entry.risk_signal else None,
                "risk_detail": entry.risk_detail,
                "notes": entry.notes,
            })
    sections["financial_metrics"] = metrics_by_category

    # ── Peer Comparison ───────────────────────────────────────────────────
    if report.peer_comparison and report.peer_comparison.peers:
        pc = report.peer_comparison
        peers_data = []
        for p in pc.peers:
            peers_data.append({
                "name": p.entity_id,
                "ticker": p.ticker,
                "tier": p.peer_tier,
                "revenue": p.revenue,
                "revenue_growth": p.revenue_growth,
                "operating_margin": p.operating_margin,
                "gross_margin": p.gross_margin,
                "rule_of_40": p.rule_of_40,
                "debt_to_equity": p.debt_to_equity,
                "current_ratio": p.current_ratio,
                "data_source": p.data_source,
                "data_is_actual": p.data_is_actual,
            })
        sections["peer_comparison"] = {
            "target": pc.target_entity,
            "peers": peers_data,
            "rationale": pc.selection_rationale,
            "comparison_metrics": pc.comparison_metrics,
        }
    else:
        sections["peer_comparison"] = None

    # ── Risk Dashboard ────────────────────────────────────────────────────
    if report.risk_dashboard:
        rd = report.risk_dashboard
        indicators = []
        for ind in rd.indicators:
            indicators.append({
                "name": ind.name,
                "category": ind.category,
                "status": ind.status.value,
                "status_color": _check_color(ind.status),
                "value": ind.value,
                "detail": ind.detail,
                "weight": ind.severity_weight,
            })
        sections["risk_dashboard"] = {
            "overall_risk": rd.overall_risk.value,
            "overall_color": _risk_color(rd.overall_risk),
            "fail_count": rd.fail_count,
            "warn_count": rd.warn_count,
            "indicators": indicators,
        }
    else:
        sections["risk_dashboard"] = None

    # ── Qualitative Findings ──────────────────────────────────────────────
    sections["qualitative_findings"] = report.qualitative_findings or []

    # ── Strengths & Risks ─────────────────────────────────────────────────
    sections["strengths"] = report.major_strengths or []
    sections["risks"] = report.major_risks or []

    # ── Recommendation ────────────────────────────────────────────────────
    sections["recommendation"] = report.recommendation_narrative or ""

    # ── Data Quality ──────────────────────────────────────────────────────
    sections["data_quality"] = {
        "notes": report.data_quality_notes or [],
        "missing_information": report.missing_information or [],
        "assumptions": report.assumptions or [],
    }

    # ── Methodology Notes ─────────────────────────────────────────────────
    sections["methodology_notes"] = report.methodology_notes or []

    return sections


def report_to_export_json(report: CreditAssessmentReport) -> Dict[str, Any]:
    """Export the full report as a JSON-serializable dict."""
    return report.model_dump()
