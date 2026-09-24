"""Liquidity metrics for the V2 fact ledger (V3).

The V2 fact ledger had profitability, solvency, saas and DSCR — but liquidity was
only produced by the old V1 calculator (a separate output). This computes liquidity
as first-class FactLedgerEntry objects so there's one source of truth, and lets the
old V1 liquidity/balance-sheet calculators be retired.

Metrics: current ratio, working capital, cash ratio. Deterministic, no LLM.
"""
from __future__ import annotations

from typing import List, Optional

from finveritas.shared.schema import CheckStatus, FactLedgerEntry, FactStatus, NormalizedCompanyRecord


def _entry(metric, name, value, unit, formula, inputs, period, risk=None, detail=None) -> FactLedgerEntry:
    return FactLedgerEntry(
        metric=metric, display_name=name, category="liquidity",
        value=round(value, 2) if value is not None else None, unit=unit,
        period=period, formula=formula, inputs_used=inputs,
        status=FactStatus.VALID if value is not None else FactStatus.INSUFFICIENT_DATA,
        risk_signal=risk, risk_detail=detail,
    )


def compute_liquidity_metrics(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    entries: List[FactLedgerEntry] = []
    ca = record.latest_value("current_assets")
    cl = record.latest_value("current_liabilities")
    cash = record.latest_value("cash_and_equivalents")
    period = None
    if record.current_assets:
        period = sorted(record.current_assets, key=lambda x: x.period)[-1].period

    # Current ratio
    if ca is not None and cl is not None and abs(cl) > 1e-9:
        cr = ca / cl
        if cr < 1.0:
            risk, detail = CheckStatus.FAIL, f"Current ratio {cr:.2f} below 1.0 — short-term assets don't cover short-term bills"
        elif cr < 1.5:
            risk, detail = CheckStatus.WARN, f"Current ratio {cr:.2f} is adequate but tight"
        else:
            risk, detail = CheckStatus.PASS, f"Current ratio {cr:.2f} is healthy"
        entries.append(_entry("current_ratio", "Current Ratio", cr, "x",
                              "Current Assets / Current Liabilities",
                              ["current_assets", "current_liabilities"], period, risk, detail))
    else:
        entries.append(_entry("current_ratio", "Current Ratio", None, "x",
                              "Current Assets / Current Liabilities",
                              ["current_assets", "current_liabilities"], period))

    # Working capital
    if ca is not None and cl is not None:
        wc = ca - cl
        risk = CheckStatus.FAIL if wc < 0 else CheckStatus.PASS
        detail = "Negative working capital — current liabilities exceed current assets" if wc < 0 else "Positive working capital"
        entries.append(_entry("working_capital", "Working Capital", wc, record.currency or "",
                              "Current Assets − Current Liabilities",
                              ["current_assets", "current_liabilities"], period, risk, detail))

    # Cash ratio
    if cash is not None and cl is not None and abs(cl) > 1e-9:
        ratio = cash / cl
        entries.append(_entry("cash_ratio", "Cash Ratio", ratio, "x",
                              "Cash & Equivalents / Current Liabilities",
                              ["cash_and_equivalents", "current_liabilities"], period))

    return entries
