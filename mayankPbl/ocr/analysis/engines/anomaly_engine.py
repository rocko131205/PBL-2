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

from shared.formatting import format_money, format_percent
from shared.schema import NormalizedCompanyRecord


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
