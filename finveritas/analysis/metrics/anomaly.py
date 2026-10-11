"""Anomaly / alert engine (V3, Phase 8).

Deterministically scans the financial time series for things a credit analyst
should look at twice: large year-on-year swings, sign flips in key lines,
accounting-identity breaks, and impossible values. Pure Python — no LLM.

These are flags for human review, not verdicts. The AI assistant can later be
asked to explain a flag, but the detection itself is deterministic.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from finveritas.shared.formatting import format_money, format_percent
from finveritas.shared.schema import NormalizedCompanyRecord


class Anomaly(BaseModel):
    field: str
    period: Optional[str] = None
    severity: str = "warning"   # info | warning | critical
    kind: str = ""
    detail: str = ""


class AnomalyReport(BaseModel):
    entity_id: str
    anomalies: List[Anomaly] = Field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for a in self.anomalies if a.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for a in self.anomalies if a.severity == "warning")


# Fields worth watching for large swings / sign flips
_SWING_FIELDS = [
    ("revenue", "Revenue"),
    ("operating_income", "Operating Income"),
    ("net_income", "Net Income"),
    ("total_assets", "Total Assets"),
    ("total_debt", "Total Debt"),
    ("equity", "Equity"),
    ("operating_cash_flow", "Operating Cash Flow"),
]
_SIGN_FIELDS = [("operating_income", "Operating Income"), ("net_income", "Net Income"),
                ("equity", "Equity"), ("free_cash_flow", "Free Cash Flow")]
_NON_NEGATIVE = [("revenue", "Revenue"), ("total_assets", "Total Assets"),
                 ("current_assets", "Current Assets")]

_SWING_WARN = 40.0    # % YoY change flagged for review
_SWING_BIG = 100.0    # % YoY change flagged more prominently


def detect_anomalies(record: NormalizedCompanyRecord) -> AnomalyReport:
    report = AnomalyReport(entity_id=record.entity_id)
    ccy = record.currency

    def series(field):
        return sorted(getattr(record, field, []), key=lambda x: x.period)

    # 1. Large YoY swings
    for field, name in _SWING_FIELDS:
        pts = series(field)
        for a, b in zip(pts, pts[1:]):
            if abs(a.value) < 1e-9:
                continue
            chg = (b.value - a.value) / abs(a.value) * 100.0
            if abs(chg) >= _SWING_WARN:
                sev = "warning" if abs(chg) < _SWING_BIG * 2 else "critical"
                report.anomalies.append(Anomaly(
                    field=field, period=b.period, severity="warning" if abs(chg) < _SWING_BIG else sev,
                    kind="large_swing",
                    detail=(f"{name} moved {format_percent(chg)} in {b.period} "
                            f"({format_money(a.value, ccy)} → {format_money(b.value, ccy)})."),
                ))

    # 2. Sign flips in key lines
    for field, name in _SIGN_FIELDS:
        pts = series(field)
        for a, b in zip(pts, pts[1:]):
            if a.value >= 0 > b.value:
                report.anomalies.append(Anomaly(
                    field=field, period=b.period, severity="warning", kind="sign_flip",
                    detail=f"{name} turned negative in {b.period} ({format_money(b.value, ccy)}).",
                ))
            elif a.value < 0 <= b.value:
                report.anomalies.append(Anomaly(
                    field=field, period=b.period, severity="info", kind="sign_flip",
                    detail=f"{name} returned to positive in {b.period} ({format_money(b.value, ccy)}).",
                ))

    # 3. Impossible values
    for field, name in _NON_NEGATIVE:
        for p in series(field):
            if p.value < 0:
                report.anomalies.append(Anomaly(
                    field=field, period=p.period, severity="critical", kind="impossible_value",
                    detail=f"{name} is negative in {p.period} ({format_money(p.value, ccy)}) — likely a data error.",
                ))

    # 4. Accounting-identity break (Assets ~= Liabilities + Equity), latest period
    ta = record.latest_value("total_assets")
    tl = record.latest_value("total_liabilities")
    eq = record.latest_value("equity")
    if ta is not None and tl is not None and eq is not None and abs(ta) > 1e-9:
        gap = abs(ta - (tl + eq)) / abs(ta)
        if gap > 0.02:  # >2% mismatch
            report.anomalies.append(Anomaly(
                field="balance_sheet", severity="warning", kind="identity_break",
                detail=(f"Balance sheet doesn't tie: Assets {format_money(ta, ccy)} vs "
                        f"Liabilities + Equity {format_money(tl + eq, ccy)} "
                        f"({gap*100:.1f}% gap)."),
            ))

    # Order: critical first, then warning, then info
    order = {"critical": 0, "warning": 1, "info": 2}
    report.anomalies.sort(key=lambda a: order.get(a.severity, 3))
    return report


# ---------------------------------------------------------------------------
# Own-history z-score monitoring (ported from DeterminX risk_monitoring)
# ---------------------------------------------------------------------------
# The scan above asks "did something swing or break?". This second lens asks "has a
# structural ratio moved abnormally versus the company's OWN history?". A ratio can
# look healthy in absolute terms and still fire here after breaking from its own range.

_ZSCORE_MIN_PERIODS = 4   # latest + at least 3 historical points to establish a range
_Z_WARN = 1.5
_Z_FAIL = 2.5


class RatioAnomaly(BaseModel):
    metric: str
    label: str
    status: str                       # PASS | WARN | FAIL | SKIP
    period: Optional[str] = None
    current: Optional[float] = None
    historical_mean: Optional[float] = None
    historical_range: Optional[List[float]] = None
    z_score: Optional[float] = None
    detail: str = ""


class RatioAnomalyScan(BaseModel):
    entity_id: str
    overall_status: str
    counts: dict
    results: List[RatioAnomaly] = Field(default_factory=list)


def _ratio_series(record: NormalizedCompanyRecord) -> dict:
    """Per-period series of the monitored ratios, using the same definitions as the ledger."""
    def s(field):
        return {p.period: p.value for p in getattr(record, field, [])}

    debt = s("total_debt") or s("total_liabilities")
    eq, ta, ca, cl = s("equity"), s("total_assets"), s("current_assets"), s("current_liabilities")
    oi, ie, ebitda, cash = s("operating_income"), s("interest_expense"), s("ebitda"), s("cash_and_equivalents")

    def ratio(num, den, scale=1.0):
        return {p: num[p] / den[p] * scale for p in num if p in den and abs(den[p]) > 1e-9}

    nd = {p: debt[p] - cash.get(p, 0.0) for p in debt}
    return {
        "debt_to_equity": ratio(debt, eq),
        "equity_ratio": ratio(eq, ta, 100.0),
        "current_ratio": ratio(ca, cl),
        "net_debt_to_ebitda": ratio(nd, ebitda),
        "interest_coverage": ratio(oi, {p: abs(v) for p, v in ie.items()}),
    }


# (metric, label, higher_is_better) -- higher_is_better=False means a RISING value is the risk direction
_MONITORED = [
    ("debt_to_equity", "Debt-to-Equity", False),
    ("equity_ratio", "Equity Ratio", True),
    ("current_ratio", "Current Ratio", True),
    ("net_debt_to_ebitda", "Net Debt / EBITDA", False),
    ("interest_coverage", "Interest Coverage", True),
]


def zscore_scan(record: NormalizedCompanyRecord) -> RatioAnomalyScan:
    """PASS/WARN/FAIL for each monitored ratio vs the company's own history. Pure Python."""
    from finveritas.analysis.metrics.extended import _util as u

    all_series = _ratio_series(record)
    results: List[RatioAnomaly] = []
    for metric, label, higher_is_better in _MONITORED:
        pts = sorted(all_series[metric].items(), key=lambda kv: u.period_key(kv[0]))
        if len(pts) < _ZSCORE_MIN_PERIODS:
            results.append(RatioAnomaly(
                metric=metric, label=label, status="SKIP",
                detail=f"Needs at least {_ZSCORE_MIN_PERIODS} periods to establish a historical range; found {len(pts)}."))
            continue
        (period, current), hist = pts[-1], [v for _, v in pts[:-1]]
        hmean, hstd = u.mean(hist), u.stdev(hist)
        hrange = [round(min(hist), 4), round(max(hist), 4)]
        if not hstd:
            # No historical variance: only range containment can be judged.
            status = "PASS" if hrange[0] <= current <= hrange[1] else "WARN"
            results.append(RatioAnomaly(
                metric=metric, label=label, status=status, period=period, current=round(current, 4),
                historical_mean=round(hmean, 4), historical_range=hrange,
                detail=f"{label} in {period} = {current:.3g}; historical range [{hrange[0]:.3g}, {hrange[1]:.3g}] "
                       "(no historical variance)."))
            continue
        z = (current - hmean) / hstd
        adverse = -z if higher_is_better else z   # positive = moving the bad way
        status = "FAIL" if adverse >= _Z_FAIL else "WARN" if adverse >= _Z_WARN else "PASS"
        side = "below" if current < hmean else "above"
        results.append(RatioAnomaly(
            metric=metric, label=label, status=status, period=period, current=round(current, 4),
            historical_mean=round(hmean, 4), historical_range=hrange, z_score=round(z, 3),
            detail=f"{label} in {period} = {current:.3g}, {abs(z):.2f} std-dev {side} its own historical mean of "
                   f"{hmean:.3g} (historical range [{hrange[0]:.3g}, {hrange[1]:.3g}])."))

    counts = {k: sum(1 for r in results if r.status == k) for k in ("PASS", "WARN", "FAIL", "SKIP")}
    # Nothing evaluated (too little history) is "SKIP", never a clean PASS.
    evaluated = counts["PASS"] + counts["WARN"] + counts["FAIL"]
    overall = "FAIL" if counts["FAIL"] else "WARN" if counts["WARN"] else "PASS" if evaluated else "SKIP"
    return RatioAnomalyScan(entity_id=record.entity_id, overall_status=overall, counts=counts, results=results)
