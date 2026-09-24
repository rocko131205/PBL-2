"""Solvency & Leverage Calculator

Deterministic computation of solvency, leverage, and debt metrics from
normalized financial data. Produces FactLedgerEntry objects.

Metrics computed:
- Debt-to-Equity Ratio
- Debt-to-Assets Ratio
- Equity Ratio (Equity / Total Assets)
- Financial Leverage (Total Assets / Equity)
- Interest Coverage Ratio (EBIT / Interest Expense)
- Net Debt (Total Debt − Cash)
- Net Debt / EBITDA

Design constraints:
- All numeric computations happen in Python (no LLM).
- Pure deterministic service.
"""
from __future__ import annotations

from typing import List, Optional

from shared.schema import (
    CheckStatus,
    FactLedgerEntry,
    FactStatus,
    NormalizedCompanyRecord,
)


def _safe_divide(numerator: float, denominator: float) -> Optional[float]:
    if abs(denominator) < 1e-9:
        return None
    return numerator / denominator


def compute_solvency_metrics(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    """Compute solvency and leverage metrics from available data."""
    entries: List[FactLedgerEntry] = []

    latest_tl = record.latest_value("total_liabilities")
    latest_eq = record.latest_value("equity")
    latest_ta = record.latest_value("total_assets")
    latest_td = record.latest_value("total_debt")
    latest_oi = record.latest_value("operating_income")
    latest_ie = record.latest_value("interest_expense")
    latest_ebitda = record.latest_value("ebitda")
    latest_cash = record.latest_value("cash_and_equivalents")

    # Determine latest period for labeling
    period = None
    if record.total_assets:
        period = sorted(record.total_assets, key=lambda x: x.period)[-1].period

    # ── Debt-to-Equity Ratio ──────────────────────────────────────────────
    # Use total_debt if available, fall back to total_liabilities
    debt_for_ratio = latest_td if latest_td is not None else latest_tl
    debt_label = "Total Debt" if latest_td is not None else "Total Liabilities"

    if debt_for_ratio is not None and latest_eq is not None:
        d2e = _safe_divide(debt_for_ratio, latest_eq)
        risk = None
        risk_detail = None
        if d2e is not None:
            if d2e > 3.0:
                risk, risk_detail = CheckStatus.FAIL, f"D/E {d2e:.2f} — very high leverage"
            elif d2e > 2.0:
                risk, risk_detail = CheckStatus.WARN, f"D/E {d2e:.2f} — elevated leverage"
            elif d2e < 0:
                risk, risk_detail = CheckStatus.FAIL, f"D/E {d2e:.2f} — negative equity (stockholders' deficit)"
            else:
                risk, risk_detail = CheckStatus.PASS, f"D/E {d2e:.2f} — manageable leverage"

        entries.append(FactLedgerEntry(
            metric="debt_to_equity",
            display_name="Debt-to-Equity Ratio",
            category="solvency",
            value=round(d2e, 2) if d2e is not None else None,
            unit="ratio",
            period=period,
            formula=f"{debt_label} / Shareholders' Equity",
            inputs_used=["total_debt" if latest_td is not None else "total_liabilities", "equity"],
            status=FactStatus.VALID if d2e is not None else FactStatus.INSUFFICIENT_DATA,
            risk_signal=risk,
            risk_detail=risk_detail,
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="debt_to_equity",
            display_name="Debt-to-Equity Ratio",
            category="solvency",
            value=None,
            unit="ratio",
            formula="Total Debt / Shareholders' Equity",
            inputs_used=["total_debt", "equity"],
            status=FactStatus.INSUFFICIENT_DATA,
        ))

    # ── Debt-to-Assets Ratio ──────────────────────────────────────────────
    if debt_for_ratio is not None and latest_ta is not None:
        d2a = _safe_divide(debt_for_ratio, latest_ta)
        risk = None
        risk_detail = None
        if d2a is not None:
            if d2a > 0.7:
                risk, risk_detail = CheckStatus.FAIL, f"D/A {d2a:.2f} — heavily leveraged"
            elif d2a > 0.5:
                risk, risk_detail = CheckStatus.WARN, f"D/A {d2a:.2f} — moderate leverage"
            else:
                risk, risk_detail = CheckStatus.PASS, f"D/A {d2a:.2f} — conservative balance sheet"

        entries.append(FactLedgerEntry(
            metric="debt_to_assets",
            display_name="Debt-to-Assets Ratio",
            category="solvency",
            value=round(d2a, 2) if d2a is not None else None,
            unit="ratio",
            period=period,
            formula=f"{debt_label} / Total Assets",
            inputs_used=["total_debt" if latest_td is not None else "total_liabilities", "total_assets"],
            status=FactStatus.VALID if d2a is not None else FactStatus.INSUFFICIENT_DATA,
            risk_signal=risk,
            risk_detail=risk_detail,
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="debt_to_assets",
            display_name="Debt-to-Assets Ratio",
            category="solvency",
            value=None,
            unit="ratio",
            formula="Total Debt / Total Assets",
            inputs_used=["total_debt", "total_assets"],
            status=FactStatus.INSUFFICIENT_DATA,
        ))

    # ── Equity Ratio ──────────────────────────────────────────────────────
    if latest_eq is not None and latest_ta is not None:
        eq_ratio = _safe_divide(latest_eq, latest_ta)
        entries.append(FactLedgerEntry(
            metric="equity_ratio",
            display_name="Equity Ratio",
            category="solvency",
            value=round(eq_ratio * 100, 2) if eq_ratio is not None else None,
            unit="%",
            period=period,
            formula="Shareholders' Equity / Total Assets × 100",
            inputs_used=["equity", "total_assets"],
            status=FactStatus.VALID if eq_ratio is not None else FactStatus.INSUFFICIENT_DATA,
        ))

    # ── Financial Leverage ────────────────────────────────────────────────
    if latest_ta is not None and latest_eq is not None:
        fl = _safe_divide(latest_ta, latest_eq)
        entries.append(FactLedgerEntry(
            metric="financial_leverage",
            display_name="Financial Leverage",
            category="solvency",
            value=round(fl, 2) if fl is not None else None,
            unit="ratio",
            period=period,
            formula="Total Assets / Shareholders' Equity",
            inputs_used=["total_assets", "equity"],
            status=FactStatus.VALID if fl is not None else FactStatus.INSUFFICIENT_DATA,
        ))

    # ── Interest Coverage Ratio ───────────────────────────────────────────
    # EBIT / Interest Expense — critical for debt servicing assessment
    if latest_oi is not None and latest_ie is not None:
        # Interest expense is often negative in financial data (it's an expense)
        ie_abs = abs(latest_ie)
        icr = _safe_divide(latest_oi, ie_abs) if ie_abs > 0 else None

        risk = None
        risk_detail = None
        if icr is not None:
            if icr < 1.0:
                risk, risk_detail = CheckStatus.FAIL, f"ICR {icr:.2f} — company cannot cover interest from operations"
            elif icr < 2.0:
                risk, risk_detail = CheckStatus.WARN, f"ICR {icr:.2f} — tight interest coverage"
            elif icr < 3.0:
                risk, risk_detail = CheckStatus.PASS, f"ICR {icr:.2f} — adequate"
            else:
                risk, risk_detail = CheckStatus.PASS, f"ICR {icr:.2f} — strong interest coverage"

        entries.append(FactLedgerEntry(
            metric="interest_coverage",
            display_name="Interest Coverage Ratio (ICR)",
            category="solvency",
            value=round(icr, 2) if icr is not None else None,
            unit="ratio",
            period=record.operating_income[-1].period if record.operating_income else period,
            formula="Operating Income (EBIT) / Interest Expense",
            inputs_used=["operating_income", "interest_expense"],
            status=FactStatus.VALID if icr is not None else FactStatus.INSUFFICIENT_DATA,
            risk_signal=risk,
            risk_detail=risk_detail,
        ))
    elif latest_ie is not None and abs(latest_ie) < 1e-9:
        # No interest expense = no debt service obligation
        entries.append(FactLedgerEntry(
            metric="interest_coverage",
            display_name="Interest Coverage Ratio (ICR)",
            category="solvency",
            value=None,
            unit="ratio",
            formula="Operating Income (EBIT) / Interest Expense",
            inputs_used=["operating_income", "interest_expense"],
            status=FactStatus.NOT_APPLICABLE,
            notes="Interest expense is zero or near-zero — no debt service obligation detected",
        ))
    else:
        entries.append(FactLedgerEntry(
            metric="interest_coverage",
            display_name="Interest Coverage Ratio (ICR)",
            category="solvency",
            value=None,
            unit="ratio",
            formula="Operating Income (EBIT) / Interest Expense",
            inputs_used=["operating_income", "interest_expense"],
            status=FactStatus.INSUFFICIENT_DATA,
        ))

    # ── Net Debt ──────────────────────────────────────────────────────────
    debt_val = latest_td if latest_td is not None else latest_tl
    if debt_val is not None:
        cash_val = latest_cash if latest_cash is not None else 0.0
        net_debt = debt_val - cash_val

        entries.append(FactLedgerEntry(
            metric="net_debt",
            display_name="Net Debt",
            category="solvency",
            value=round(net_debt, 2),
            unit="absolute",
            period=period,
            formula="Total Debt − Cash & Equivalents",
            inputs_used=["total_debt" if latest_td is not None else "total_liabilities", "cash_and_equivalents"],
            status=FactStatus.VALID,
            notes="Negative net debt means the company has more cash than debt" if net_debt < 0 else None,
        ))

        # ── Net Debt / EBITDA ─────────────────────────────────────────────
        if latest_ebitda is not None:
            nd_ebitda = _safe_divide(net_debt, latest_ebitda)
            risk = None
            risk_detail = None
            if nd_ebitda is not None:
                if nd_ebitda > 4.0:
                    risk, risk_detail = CheckStatus.FAIL, f"Net Debt/EBITDA {nd_ebitda:.1f}x — high leverage"
                elif nd_ebitda > 2.5:
                    risk, risk_detail = CheckStatus.WARN, f"Net Debt/EBITDA {nd_ebitda:.1f}x — moderate leverage"
                elif nd_ebitda < 0:
                    risk, risk_detail = CheckStatus.PASS, f"Net Debt/EBITDA {nd_ebitda:.1f}x — net cash position"
                else:
                    risk, risk_detail = CheckStatus.PASS, f"Net Debt/EBITDA {nd_ebitda:.1f}x — manageable"

            entries.append(FactLedgerEntry(
                metric="net_debt_to_ebitda",
                display_name="Net Debt / EBITDA",
                category="solvency",
                value=round(nd_ebitda, 2) if nd_ebitda is not None else None,
                unit="ratio",
                period=period,
                formula="Net Debt / EBITDA",
                inputs_used=["net_debt", "ebitda"],
                status=FactStatus.VALID if nd_ebitda is not None else FactStatus.INSUFFICIENT_DATA,
                risk_signal=risk,
                risk_detail=risk_detail,
            ))

    return entries
