"""Profitability Calculator

Deterministic computation of profitability metrics from normalized financial data.
Produces FactLedgerEntry objects for the immutable fact ledger.

Metrics computed:
- Gross Margin (%)
- Operating Margin / EBIT Margin (%)
- EBITDA Margin (%)
- Net Profit Margin (%)
- Return on Equity (ROE) (%)
- Return on Assets (ROA) (%)
- Return on Capital Employed (ROCE) (%)

Design constraints:
- All numeric computations happen in Python (no LLM).
- Pure deterministic service.
- Returns FactLedgerEntry objects with provenance and methodology.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schema import (
    CheckStatus,
    FactLedgerEntry,
    FactStatus,
    NormalizedCompanyRecord,
)


def _safe_divide(numerator: float, denominator: float) -> Optional[float]:
    """Safe division that returns None if denominator is zero or near-zero."""
    if abs(denominator) < 1e-9:
        return None
    return numerator / denominator


def _safe_pct(numerator: float, denominator: float) -> Optional[float]:
    """Return percentage or None if denominator is zero."""
    result = _safe_divide(numerator, denominator)
    return result * 100.0 if result is not None else None


def compute_profitability_metrics(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    """Compute profitability metrics from a NormalizedCompanyRecord.

    Returns a list of FactLedgerEntry objects. Metrics are only computed
    when the required input data is available — never fabricated.
    """
    entries: List[FactLedgerEntry] = []
    latest_rev = record.latest_value("revenue")

    # ── Gross Margin ──────────────────────────────────────────────────────
    latest_gp = record.latest_value("gross_profit")
    if latest_rev is not None and latest_gp is not None:
        gm = _safe_pct(latest_gp, latest_rev)
        status = FactStatus.VALID if gm is not None else FactStatus.INSUFFICIENT_DATA
        risk = None
        risk_detail = None
        if gm is not None:
            if gm < 30:
                risk, risk_detail = CheckStatus.FAIL, f"Gross margin {gm:.1f}% is critically low"
            elif gm < 50:
                risk, risk_detail = CheckStatus.WARN, f"Gross margin {gm:.1f}% is below typical SaaS levels (>60%)"
            else:
                risk, risk_detail = CheckStatus.PASS, f"Gross margin {gm:.1f}% is healthy"

        entries.append(FactLedgerEntry(
            metric="gross_margin",
            display_name="Gross Margin",
            category="profitability",
            value=round(gm, 2) if gm is not None else None,
            unit="%",
            period=record.gross_profit[-1].period if record.gross_profit else None,
            formula="Gross Profit / Revenue × 100",
            inputs_used=["gross_profit", "revenue"],
            status=status,
            risk_signal=risk,
            risk_detail=risk_detail,
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="gross_margin",
            display_name="Gross Margin",
            category="profitability",
            value=None,
            unit="%",
            formula="Gross Profit / Revenue × 100",
            inputs_used=["gross_profit", "revenue"],
            status=FactStatus.INSUFFICIENT_DATA,
            notes=f"Missing: {'gross_profit' if latest_gp is None else ''} {'revenue' if latest_rev is None else ''}".strip(),
        ))

    # ── Operating Margin ──────────────────────────────────────────────────
    latest_oi = record.latest_value("operating_income")
    if latest_rev is not None and latest_oi is not None:
        om = _safe_pct(latest_oi, latest_rev)
        status = FactStatus.VALID if om is not None else FactStatus.INSUFFICIENT_DATA
        risk = None
        risk_detail = None
        if om is not None:
            if om < 0:
                risk, risk_detail = CheckStatus.FAIL, f"Operating margin {om:.1f}% is negative — operating losses"
            elif om < 10:
                risk, risk_detail = CheckStatus.WARN, f"Operating margin {om:.1f}% is thin"
            else:
                risk, risk_detail = CheckStatus.PASS, f"Operating margin {om:.1f}% is healthy"

        entries.append(FactLedgerEntry(
            metric="operating_margin",
            display_name="Operating Margin",
            category="profitability",
            value=round(om, 2) if om is not None else None,
            unit="%",
            period=record.operating_income[-1].period if record.operating_income else None,
            formula="Operating Income / Revenue × 100",
            inputs_used=["operating_income", "revenue"],
            status=status,
            risk_signal=risk,
            risk_detail=risk_detail,
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="operating_margin",
            display_name="Operating Margin",
            category="profitability",
            value=None,
            unit="%",
            formula="Operating Income / Revenue × 100",
            inputs_used=["operating_income", "revenue"],
            status=FactStatus.INSUFFICIENT_DATA,
        ))

    # ── EBITDA Margin ─────────────────────────────────────────────────────
    latest_ebitda = record.latest_value("ebitda")
    if latest_rev is not None and latest_ebitda is not None:
        em = _safe_pct(latest_ebitda, latest_rev)
        entries.append(FactLedgerEntry(
            metric="ebitda_margin",
            display_name="EBITDA Margin",
            category="profitability",
            value=round(em, 2) if em is not None else None,
            unit="%",
            period=record.ebitda[-1].period if record.ebitda else None,
            formula="EBITDA / Revenue × 100",
            inputs_used=["ebitda", "revenue"],
            status=FactStatus.VALID if em is not None else FactStatus.INSUFFICIENT_DATA,
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="ebitda_margin",
            display_name="EBITDA Margin",
            category="profitability",
            value=None,
            unit="%",
            formula="EBITDA / Revenue × 100",
            inputs_used=["ebitda", "revenue"],
            status=FactStatus.INSUFFICIENT_DATA,
        ))

    # ── Net Profit Margin ─────────────────────────────────────────────────
    latest_ni = record.latest_value("net_income")
    if latest_rev is not None and latest_ni is not None:
        npm = _safe_pct(latest_ni, latest_rev)
        risk = None
        risk_detail = None
        if npm is not None:
            if npm < -10:
                risk, risk_detail = CheckStatus.FAIL, f"Net margin {npm:.1f}% — significant net losses"
            elif npm < 0:
                risk, risk_detail = CheckStatus.WARN, f"Net margin {npm:.1f}% — company is unprofitable"
            else:
                risk, risk_detail = CheckStatus.PASS, f"Net margin {npm:.1f}%"

        entries.append(FactLedgerEntry(
            metric="net_profit_margin",
            display_name="Net Profit Margin",
            category="profitability",
            value=round(npm, 2) if npm is not None else None,
            unit="%",
            period=record.net_income[-1].period if record.net_income else None,
            formula="Net Income / Revenue × 100",
            inputs_used=["net_income", "revenue"],
            status=FactStatus.VALID if npm is not None else FactStatus.INSUFFICIENT_DATA,
            risk_signal=risk,
            risk_detail=risk_detail,
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="net_profit_margin",
            display_name="Net Profit Margin",
            category="profitability",
            value=None,
            unit="%",
            formula="Net Income / Revenue × 100",
            inputs_used=["net_income", "revenue"],
            status=FactStatus.INSUFFICIENT_DATA,
        ))

    # ── Return on Equity (ROE) ────────────────────────────────────────────
    latest_eq = record.latest_value("equity")
    if latest_ni is not None and latest_eq is not None:
        roe = _safe_pct(latest_ni, latest_eq)
        risk = None
        risk_detail = None
        if roe is not None:
            if roe < 0:
                risk, risk_detail = CheckStatus.WARN, f"ROE {roe:.1f}% is negative"
            elif roe > 30:
                risk, risk_detail = CheckStatus.PASS, f"ROE {roe:.1f}% — strong return on equity"
            else:
                risk, risk_detail = CheckStatus.PASS, f"ROE {roe:.1f}%"

        entries.append(FactLedgerEntry(
            metric="roe",
            display_name="Return on Equity (ROE)",
            category="profitability",
            value=round(roe, 2) if roe is not None else None,
            unit="%",
            period=record.net_income[-1].period if record.net_income else None,
            formula="Net Income / Shareholders' Equity × 100",
            inputs_used=["net_income", "equity"],
            status=FactStatus.VALID if roe is not None else FactStatus.INSUFFICIENT_DATA,
            risk_signal=risk,
            risk_detail=risk_detail,
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="roe",
            display_name="Return on Equity (ROE)",
            category="profitability",
            value=None,
            unit="%",
            formula="Net Income / Shareholders' Equity × 100",
            inputs_used=["net_income", "equity"],
            status=FactStatus.INSUFFICIENT_DATA,
        ))

    # ── Return on Assets (ROA) ────────────────────────────────────────────
    latest_ta = record.latest_value("total_assets")
    if latest_ni is not None and latest_ta is not None:
        roa = _safe_pct(latest_ni, latest_ta)
        entries.append(FactLedgerEntry(
            metric="roa",
            display_name="Return on Assets (ROA)",
            category="profitability",
            value=round(roa, 2) if roa is not None else None,
            unit="%",
            period=record.net_income[-1].period if record.net_income else None,
            formula="Net Income / Total Assets × 100",
            inputs_used=["net_income", "total_assets"],
            status=FactStatus.VALID if roa is not None else FactStatus.INSUFFICIENT_DATA,
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="roa",
            display_name="Return on Assets (ROA)",
            category="profitability",
            value=None,
            unit="%",
            formula="Net Income / Total Assets × 100",
            inputs_used=["net_income", "total_assets"],
            status=FactStatus.INSUFFICIENT_DATA,
        ))

    # ── Return on Capital Employed (ROCE) ─────────────────────────────────
    latest_tl = record.latest_value("total_liabilities")
    latest_cl = record.latest_value("current_liabilities")
    if latest_oi is not None and latest_ta is not None and latest_cl is not None:
        capital_employed = latest_ta - latest_cl
        roce = _safe_pct(latest_oi, capital_employed)
        entries.append(FactLedgerEntry(
            metric="roce",
            display_name="Return on Capital Employed (ROCE)",
            category="profitability",
            value=round(roce, 2) if roce is not None else None,
            unit="%",
            period=record.operating_income[-1].period if record.operating_income else None,
            formula="Operating Income / (Total Assets − Current Liabilities) × 100",
            inputs_used=["operating_income", "total_assets", "current_liabilities"],
            status=FactStatus.VALID if roce is not None else FactStatus.INSUFFICIENT_DATA,
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="roce",
            display_name="Return on Capital Employed (ROCE)",
            category="profitability",
            value=None,
            unit="%",
            formula="Operating Income / (Total Assets − Current Liabilities) × 100",
            inputs_used=["operating_income", "total_assets", "current_liabilities"],
            status=FactStatus.INSUFFICIENT_DATA,
        ))

    return entries
