"""Working-capital credit assessment (Tandon Method II style).

Ported from DeterminX ``src/credit/working_capital_agent.py`` (the deterministic
half). Two honesty rules are structural, not stylistic:

* Maximum Permissible Bank Finance (MPBF) is ALWAYS ``ESTIMATED``. It is derived
  from the balance sheet alone, so it is never presented as a bank-sanctioned limit.
* Drawing Power is ALWAYS ``REQUIRES_ADDITIONAL_DOCUMENT``. It needs the bank's
  margin percentages and stock/receivables ageing from a sanction letter, so there
  is no code path that returns a number for it.

DSO / DIO / DPO / CCC are produced by ``working_capital.py``; here we only add the
Tandon terms and the operating cycle.
"""
from __future__ import annotations

from typing import List

from finveritas.shared.schema import FactLedgerEntry, FactStatus, NormalizedCompanyRecord

from . import _util as u

CATEGORY = "credit"
MIN_NWC_PCT = 0.25  # Tandon Method II stipulated minimum net working capital, as a share of TCA

_TANDON_METRICS = [
    ("gross_working_capital", "Gross Working Capital"),
    ("working_capital_gap", "Working Capital Gap"),
    ("minimum_stipulated_nwc", "Minimum Stipulated NWC"),
    ("estimated_mpbf", "Estimated MPBF"),
    ("current_asset_coverage_ratio", "Current Asset Coverage Ratio"),
]


def compute_credit(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    out: List[FactLedgerEntry] = []
    periods = u.common_periods(record, ["current_assets", "current_liabilities"])
    if not periods:
        reason = "Needs current assets and current liabilities."
        out.extend(u.unavailable(m, n, CATEGORY, reason) for m, n in _TANDON_METRICS)
    else:
        p = periods[-1]
        tca = u.series(record, "current_assets")[p]
        cl = u.series(record, "current_liabilities")[p]
        inputs = ["current_assets", "current_liabilities"]
        note = ("Estimated from the balance sheet alone; current liabilities here include all current "
                "liabilities, not only bank borrowings. Not a bank-sanctioned figure.")
        gap = tca - cl
        min_nwc = tca * MIN_NWC_PCT
        out.append(u.entry("gross_working_capital", "Gross Working Capital", CATEGORY, tca, "absolute", p,
                           "Total Current Assets (TCA), as reported", ["current_assets"]))
        out.append(u.entry("working_capital_gap", "Working Capital Gap", CATEGORY, gap, "absolute", p,
                           "TCA - Current Liabilities (Tandon Method II)", inputs,
                           status=FactStatus.ESTIMATED, notes=note))
        out.append(u.entry("minimum_stipulated_nwc", "Minimum Stipulated NWC", CATEGORY, min_nwc, "absolute", p,
                           f"{MIN_NWC_PCT:.0%} of TCA (Tandon Method II stipulated minimum)", ["current_assets"],
                           status=FactStatus.ESTIMATED, notes="Applies the standard 25% stipulation."))
        out.append(u.entry("estimated_mpbf", "Estimated MPBF", CATEGORY, gap - min_nwc, "absolute", p,
                           "Working Capital Gap - Minimum Stipulated NWC (Tandon Method II)", inputs,
                           status=FactStatus.ESTIMATED,
                           notes=note + " Real MPBF also needs sanctioned limits, ageing and CMA data."))
        if cl:
            out.append(u.entry("current_asset_coverage_ratio", "Current Asset Coverage Ratio", CATEGORY,
                               tca / cl, "ratio", p, "Current Assets / Current Liabilities", inputs))
        else:
            out.append(u.unavailable("current_asset_coverage_ratio", "Current Asset Coverage Ratio", CATEGORY,
                                     "Current liabilities are zero in the latest period."))

    out.append(u.requires_document(
        "estimated_drawing_power", "Estimated Drawing Power", CATEGORY,
        "Drawing Power needs the bank's inventory and receivables margin percentages from the sanction "
        "letter, plus current stock and receivables ageing. None of that is in a financial statement, so "
        "it is never estimated from the balance sheet.",
        "(Paid stock x (1 - inventory margin)) + (eligible receivables x (1 - receivables margin)) - creditors"))

    # Operating cycle = DSO + DIO, using the same definitions as working_capital.py.
    rev, cogs = u.series(record, "revenue"), u.series(record, "cost_of_revenue")
    ar, inv = u.series(record, "accounts_receivable"), u.series(record, "inventory")
    for p in sorted(set(rev) & set(cogs) & set(ar) & set(inv), key=u.period_key, reverse=True):
        if rev[p] and cogs[p]:
            cycle = ar[p] / rev[p] * u.DAYS_IN_YEAR + inv[p] / cogs[p] * u.DAYS_IN_YEAR
            out.append(u.entry("operating_cycle", "Operating Cycle", CATEGORY, cycle, "days", p,
                               "DSO + DIO", ["accounts_receivable", "revenue", "inventory", "cost_of_revenue"]))
            break
    else:
        out.append(u.unavailable("operating_cycle", "Operating Cycle", CATEGORY,
                                 "Needs receivables, inventory, revenue and cost of revenue."))
    return out
