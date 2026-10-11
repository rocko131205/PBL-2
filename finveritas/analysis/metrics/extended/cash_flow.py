"""Cash-flow intelligence (ported from DeterminX ``metrics/cash_flow.py``)."""
from __future__ import annotations

from typing import List

from finveritas.shared.schema import FactLedgerEntry, NormalizedCompanyRecord

from . import _util as u

CATEGORY = "cash_flow"

_DIRECT = [
    ("operating_cash_flow", "Operating Cash Flow"),
    ("investing_cash_flow", "Investing Cash Flow"),
    ("financing_cash_flow", "Financing Cash Flow"),
    ("capital_expenditure", "Capital Expenditure"),
]


def compute_cash_flow(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    out: List[FactLedgerEntry] = []
    for field, label in _DIRECT:
        latest = u.latest_point(u.series(record, field))
        metric = f"cf_{field}"
        if latest is None:
            out.append(u.unavailable(metric, label, CATEGORY,
                                     f"Needs '{field}' from a cash-flow statement; none was ingested."))
        else:
            out.append(u.entry(metric, label, CATEGORY, latest[1], "absolute", latest[0],
                               "As reported (cash-flow statement)", [field]))

    # Free cash flow = OCF - |capex|, in the latest period both exist.
    periods = u.common_periods(record, ["operating_cash_flow", "capital_expenditure"])
    if periods:
        p = periods[-1]
        fcf = u.series(record, "operating_cash_flow")[p] - abs(u.series(record, "capital_expenditure")[p])
        out.append(u.entry("cf_free_cash_flow", "Free Cash Flow", CATEGORY, fcf, "absolute", p,
                           "Operating Cash Flow - |CapEx|", ["operating_cash_flow", "capital_expenditure"]))
    else:
        out.append(u.unavailable("cf_free_cash_flow", "Free Cash Flow", CATEGORY,
                                 "Needs operating cash flow and capital expenditure."))

    periods = u.common_periods(record, ["operating_cash_flow", "current_liabilities"])
    if periods:
        p = periods[-1]
        cl = u.series(record, "current_liabilities")[p]
        if cl:
            out.append(u.entry("operating_cash_flow_ratio", "Operating Cash Flow Ratio", CATEGORY,
                               u.series(record, "operating_cash_flow")[p] / cl, "ratio", p,
                               "Operating Cash Flow / Current Liabilities",
                               ["operating_cash_flow", "current_liabilities"]))
        else:
            out.append(u.unavailable("operating_cash_flow_ratio", "Operating Cash Flow Ratio", CATEGORY,
                                     "Current liabilities are zero in the latest period."))
    else:
        out.append(u.unavailable("operating_cash_flow_ratio", "Operating Cash Flow Ratio", CATEGORY,
                                 "Needs operating cash flow and current liabilities."))

    ocf = u.series(record, "operating_cash_flow")
    if ocf:
        p = max(ocf, key=u.period_key)
        burn = abs(ocf[p]) if ocf[p] < 0 else 0.0
        out.append(u.entry("cash_burn", "Cash Burn", CATEGORY, burn, "absolute", p,
                           "|Operating Cash Flow| when negative in the latest period, otherwise 0",
                           ["operating_cash_flow"]))
    return out
