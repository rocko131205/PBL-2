"""Revenue, growth and trend intelligence.

Ported from DeterminX ``metrics/revenue.py``, ``growth.py`` and ``trends.py``.
Revenue growth/CAGR feed the assumption-validation reference range, so the
metric names here (``revenue_cagr``, ``revenue_yoy_growth_avg``) are a contract.
"""
from __future__ import annotations

from typing import List

from finveritas.shared.schema import FactLedgerEntry, NormalizedCompanyRecord

from . import _util as u

REVENUE = "revenue"
GROWTH = "growth"
TREND = "trend"

# metric prefix -> (record field, label). EBIT reuses operating_income, as elsewhere in the project.
_GROWTH_FIELDS = {
    "ebitda": ("ebitda", "EBITDA"),
    "pat": ("net_income", "Net Profit (PAT)"),
    "ebit": ("operating_income", "EBIT"),
    "asset": ("total_assets", "Total Assets"),
    "equity": ("equity", "Equity"),
    "cash_flow": ("operating_cash_flow", "Operating Cash Flow"),
}

_TREND_FIELDS = {
    "revenue_trend": ("revenue", "Revenue"),
    "profit_trend": ("net_income", "Net Profit (PAT)"),
    "debt_trend": ("total_debt", "Total Debt"),
    "cash_flow_trend": ("operating_cash_flow", "Operating Cash Flow"),
}


def _growth_block(record: NormalizedCompanyRecord, prefix: str, field: str, label: str,
                  category: str, *, with_avg: bool) -> List[FactLedgerEntry]:
    out: List[FactLedgerEntry] = []
    periods = u.common_periods(record, [field])
    if len(periods) < 2:
        out.append(u.unavailable(f"{prefix}_growth", f"{label} Growth (YoY)", category,
                                 f"Need at least 2 periods of '{field}'."))
        out.append(u.unavailable(f"{prefix}_cagr", f"{label} CAGR", category,
                                 f"Need at least 2 periods of '{field}'."))
        return out
    values = u.aligned(record, field, periods)
    yoy = u.yoy_pct(values)
    if yoy[-1] is not None:
        out.append(u.entry(f"{prefix}_growth", f"{label} Growth (YoY)", category, yoy[-1], "%", periods[-1],
                           f"({field}[t] - {field}[t-1]) / |{field}[t-1]| x 100", [field]))
    else:
        out.append(u.unavailable(f"{prefix}_growth", f"{label} Growth (YoY)", category,
                                 f"Prior-period '{field}' is zero."))
    if with_avg:
        vals = [g for g in yoy if g is not None]
        if vals:
            out.append(u.entry(f"{prefix}_yoy_growth_avg", f"{label} Average YoY Growth", category,
                               u.mean(vals), "%", u.MULTI, f"mean of YoY {field} growth over all periods", [field]))
    intervals = len(values) - 1
    cagr = u.cagr_pct(values[0], values[-1], intervals)
    if cagr is not None:
        out.append(u.entry(f"{prefix}_cagr", f"{label} CAGR", category, cagr, "%", u.MULTI,
                           f"(({field}[{periods[-1]}] / {field}[{periods[0]}]) ^ (1/{intervals}) - 1) x 100", [field]))
    else:
        out.append(u.unavailable(f"{prefix}_cagr", f"{label} CAGR", category,
                                 "CAGR needs a positive first and last value."))
    return out


def compute_revenue(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    out = _growth_block(record, "revenue", "revenue", "Revenue", REVENUE, with_avg=True)
    periods = u.common_periods(record, ["revenue"])
    if len(periods) >= 3:
        out.append(u.entry("revenue_trend_direction", "Revenue Trend", REVENUE,
                           u.trend_direction(u.aligned(record, "revenue", periods)), "label", u.MULTI,
                           "Sign and size of the OLS slope of revenue vs period, normalised by mean revenue",
                           ["revenue"]))
    return out


def compute_growth(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    out: List[FactLedgerEntry] = []
    for prefix, (field, label) in _GROWTH_FIELDS.items():
        out.extend(_growth_block(record, prefix, field, label, GROWTH, with_avg=False))
    return out


def compute_trends(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    out: List[FactLedgerEntry] = []
    for metric, (field, label) in _TREND_FIELDS.items():
        periods = u.common_periods(record, [field])
        if len(periods) < 3:
            out.append(u.unavailable(metric, f"{label} Trend", TREND,
                                     f"Need at least 3 periods of '{field}' to classify a trend; found {len(periods)}."))
            continue
        out.append(u.entry(metric, f"{label} Trend", TREND, u.trend_direction(u.aligned(record, field, periods)),
                           "label", u.MULTI,
                           f"Sign and size of the OLS slope of {label} vs period, normalised by mean {label}", [field]))
    periods = u.common_periods(record, ["revenue", "net_income"])
    margins = [n / r for n, r in zip(u.aligned(record, "net_income", periods), u.aligned(record, "revenue", periods)) if r]
    if len(periods) >= 3 and len(margins) >= 3:
        out.append(u.entry("margin_trend", "Net Margin Trend", TREND, u.trend_direction(margins), "label", u.MULTI,
                           "OLS slope of net profit margin (net income / revenue) vs period", ["net_income", "revenue"]))
    else:
        out.append(u.unavailable("margin_trend", "Net Margin Trend", TREND,
                                 "Need at least 3 periods with both revenue and net income."))
    return out
