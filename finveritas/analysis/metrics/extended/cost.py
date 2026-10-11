"""Cost intelligence (ported from DeterminX ``metrics/cost.py``)."""
from __future__ import annotations

from typing import List

from finveritas.shared.schema import FactLedgerEntry, FactStatus, NormalizedCompanyRecord

from . import _util as u

CATEGORY = "cost"

_SIMPLE = [
    ("cost_of_revenue", "Cost of Revenue", "As reported (COGS / cost of sales)"),
    ("sga_expense", "SG&A Expense", "As reported (selling, general & administrative)"),
    ("rd_expense", "R&D Expense", "As reported (research & development)"),
    ("depreciation", "Depreciation & Amortization", "As reported (may include amortization when not split out)"),
    ("amortization", "Amortization", "As reported, only when disclosed separately from depreciation"),
]


def compute_cost(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    out: List[FactLedgerEntry] = []
    for field, label, formula in _SIMPLE:
        latest = u.latest_point(u.series(record, field))
        if latest is None:
            out.append(u.unavailable(f"cost_{field}", label, CATEGORY, f"No '{field}' data in the ingested statements."))
            continue
        out.append(u.entry(f"cost_{field}", label, CATEGORY, latest[1], "absolute", latest[0], formula, [field]))

    # Operating expenses: sum of the components actually present, else a disclosed residual.
    periods = u.common_periods(record, ["sga_expense", "rd_expense"])
    if periods:
        p = periods[-1]
        total = (u.series(record, "sga_expense")[p] + u.series(record, "rd_expense")[p]
                 + u.series(record, "depreciation").get(p, 0.0))
        out.append(u.entry("operating_expenses", "Operating Expenses", CATEGORY, total, "absolute", p,
                           "SG&A + R&D + Depreciation (only components present are summed)",
                           ["sga_expense", "rd_expense", "depreciation"]))
        return out
    periods = u.common_periods(record, ["revenue", "cost_of_revenue", "operating_income"])
    if periods:
        p = periods[-1]
        v = (u.series(record, "revenue")[p] - u.series(record, "cost_of_revenue")[p]
             - u.series(record, "operating_income")[p])
        out.append(u.entry("operating_expenses", "Operating Expenses", CATEGORY, v, "absolute", p,
                           "Revenue - Cost of Revenue - Operating Income (residual, derived)",
                           ["revenue", "cost_of_revenue", "operating_income"], status=FactStatus.ESTIMATED,
                           notes="Derived as a residual; no separate operating-expense line was ingested."))
    else:
        out.append(u.unavailable("operating_expenses", "Operating Expenses", CATEGORY,
                                 "Needs SG&A + R&D, or revenue, cost of revenue and operating income."))
    return out
