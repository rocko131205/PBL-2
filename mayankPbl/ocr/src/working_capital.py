"""Working-capital cycle engine (V3).

The cash conversion cycle tells a lender how long cash is tied up in operations —
a core credit signal, especially for lending against working capital.

  DSO = Accounts Receivable / Revenue        x 365   (days to collect from customers)
  DIO = Inventory          / Cost of Revenue x 365   (days inventory is held)
  DPO = Accounts Payable   / Cost of Revenue x 365   (days taken to pay suppliers)
  CCC = DSO + DIO - DPO                              (net days cash is tied up)

Lower CCC is better. Deterministic; produces fact-ledger entries.
"""
from __future__ import annotations

from typing import List, Optional

from .schema import CheckStatus, FactLedgerEntry, FactStatus, NormalizedCompanyRecord


def _entry(metric, name, value, formula, inputs, period, risk=None, detail=None) -> FactLedgerEntry:
    return FactLedgerEntry(
        metric=metric, display_name=name, category="working_capital",
        value=round(value, 1) if value is not None else None, unit="days",
        period=period, formula=formula, inputs_used=inputs,
        status=FactStatus.VALID if value is not None else FactStatus.INSUFFICIENT_DATA,
        risk_signal=risk, risk_detail=detail,
    )


def compute_working_capital_cycle(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    entries: List[FactLedgerEntry] = []
    rev = record.latest_value("revenue")
    cogs = record.latest_value("cost_of_revenue")
    ar = record.latest_value("accounts_receivable")
    inv = record.latest_value("inventory")
    ap = record.latest_value("accounts_payable")
    period = None
    if record.revenue:
        period = sorted(record.revenue, key=lambda x: x.period)[-1].period

    dso = dio = dpo = None

    if ar is not None and rev and abs(rev) > 1e-9:
        dso = ar / rev * 365
        entries.append(_entry("dso", "Days Sales Outstanding (DSO)", dso,
                              "Accounts Receivable / Revenue x 365",
                              ["accounts_receivable", "revenue"], period))
    if inv is not None and cogs and abs(cogs) > 1e-9:
        dio = inv / cogs * 365
        entries.append(_entry("dio", "Days Inventory Outstanding (DIO)", dio,
                              "Inventory / Cost of Revenue x 365",
                              ["inventory", "cost_of_revenue"], period))
    if ap is not None and cogs and abs(cogs) > 1e-9:
        dpo = ap / cogs * 365
        entries.append(_entry("dpo", "Days Payable Outstanding (DPO)", dpo,
                              "Accounts Payable / Cost of Revenue x 365",
                              ["accounts_payable", "cost_of_revenue"], period))

    # Cash conversion cycle needs at least DSO and DIO (DPO optional -> treated as 0).
    if dso is not None and dio is not None:
        ccc = dso + dio - (dpo or 0.0)
        if ccc <= 30:
            risk, detail = CheckStatus.PASS, f"Cash conversion cycle {ccc:.0f} days is short — cash isn't tied up long."
        elif ccc <= 90:
            risk, detail = CheckStatus.WARN, f"Cash conversion cycle {ccc:.0f} days is moderate."
        else:
            risk, detail = CheckStatus.FAIL, f"Cash conversion cycle {ccc:.0f} days is long — significant cash tied up in operations."
        entries.append(_entry("cash_conversion_cycle", "Cash Conversion Cycle (CCC)", ccc,
                              "DSO + DIO - DPO", ["dso", "dio", "dpo"], period, risk, detail))

    return entries
