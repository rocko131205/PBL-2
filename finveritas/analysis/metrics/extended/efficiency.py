"""Efficiency and return intelligence.

Ported from DeterminX ``metrics/efficiency.py`` and ``metrics/returns.py``.

Left out on purpose: DSO / DIO / DPO / cash conversion cycle (already produced by
``working_capital.py``) and ROE / ROA / ROCE (already produced by
``profitability.py``). One source of truth per number.
"""
from __future__ import annotations

from typing import List, Optional

from finveritas.shared.schema import FactLedgerEntry, NormalizedCompanyRecord

from . import _util as u

EFFICIENCY = "efficiency"
RETURNS = "returns"

# metric, label, flow field, balance field, formula
_TURNOVERS = [
    ("asset_turnover", "Asset Turnover", "revenue", "total_assets", "Revenue / average(Total Assets)"),
    ("receivable_turnover", "Receivables Turnover", "revenue", "accounts_receivable",
     "Revenue / average(Accounts Receivable)"),
    ("payable_turnover", "Payables Turnover", "cost_of_revenue", "accounts_payable",
     "Cost of Revenue / average(Accounts Payable)"),
    ("inventory_turnover", "Inventory Turnover", "cost_of_revenue", "inventory",
     "Cost of Revenue / average(Inventory)"),
    ("fixed_asset_turnover", "Fixed Asset Turnover", "revenue", "non_current_assets",
     "Revenue / average(Non-Current Assets)"),
]


def _average_balance(record: NormalizedCompanyRecord, field: str, period: str) -> Optional[float]:
    """Average of the opening and closing balance when a prior period exists, else the closing balance."""
    bal = u.series(record, field)
    ordered = sorted(bal, key=u.period_key)
    if period not in bal:
        return None
    i = ordered.index(period)
    return (bal[period] + bal[ordered[i - 1]]) / 2.0 if i > 0 else bal[period]


def compute_efficiency(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    out: List[FactLedgerEntry] = []
    for metric, label, flow_f, bal_f, formula in _TURNOVERS:
        periods = u.common_periods(record, [flow_f, bal_f])
        done = False
        for p in reversed(periods):
            avg = _average_balance(record, bal_f, p)
            if avg:
                out.append(u.entry(metric, label, EFFICIENCY, u.series(record, flow_f)[p] / avg, "ratio", p,
                                   formula, [flow_f, bal_f]))
                done = True
                break
        if not done:
            out.append(u.unavailable(metric, label, EFFICIENCY,
                                     f"Needs '{flow_f}' and a non-zero '{bal_f}' in the same period."))

    periods = u.common_periods(record, ["revenue", "current_assets", "current_liabilities"])
    for p in reversed(periods):
        wc = u.series(record, "current_assets")[p] - u.series(record, "current_liabilities")[p]
        if wc:
            out.append(u.entry("working_capital_turnover", "Working Capital Turnover", EFFICIENCY,
                               u.series(record, "revenue")[p] / wc, "ratio", p, "Revenue / Working Capital",
                               ["revenue", "current_assets", "current_liabilities"]))
            break
    else:
        out.append(u.unavailable("working_capital_turnover", "Working Capital Turnover", EFFICIENCY,
                                 "Needs revenue, current assets and current liabilities with non-zero working capital."))
    return out


def compute_returns(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    """ROIC only; ROE/ROA/ROCE come from the profitability engine."""
    fields = ["operating_income", "income_tax", "pretax_income", "total_debt", "equity", "cash_and_equivalents"]
    for p in reversed(u.common_periods(record, fields)):
        s = {f: u.series(record, f)[p] for f in fields}
        invested = s["total_debt"] + s["equity"] - s["cash_and_equivalents"]
        if not invested:
            continue
        rate = min(max(s["income_tax"] / s["pretax_income"], 0.0), 1.0) if s["pretax_income"] else 0.0
        nopat = s["operating_income"] * (1 - rate)
        return [u.entry("roic", "Return on Invested Capital (ROIC)", RETURNS, nopat / invested * 100, "%", p,
                        "NOPAT / Invested Capital x 100; NOPAT = EBIT x (1 - effective tax rate), "
                        "Invested Capital = Total Debt + Equity - Cash", fields)]
    return [u.unavailable("roic", "Return on Invested Capital (ROIC)", RETURNS,
                          "Needs operating income, tax, pre-tax income, debt, equity and cash in one period.")]
