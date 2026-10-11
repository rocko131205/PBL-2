"""Shared helpers for the extended (intelligence-layer) metrics.

Every module in this package is a pure function ``NormalizedCompanyRecord ->
List[FactLedgerEntry]``. Conventions:

* One entry per metric holding the LATEST computable period (``period`` = that
  period), plus ``period="multi-period"`` entries for whole-series summaries
  such as CAGR, average growth and trend direction.
* A metric that cannot be computed yields ONE entry with ``value=None``, a
  status saying why (``INSUFFICIENT_DATA`` / ``REQUIRES_ADDITIONAL_DOCUMENT`` /
  ``REQUIRES_EXTERNAL_DATA``) and the reason in ``notes`` -- never a guess.
* ``ESTIMATED`` is only used when a disclosed simplifying assumption is applied.
* These entries deliberately carry no ``risk_signal``: they are advisory and
  must not move the existing risk dashboard, scorecard or verdict.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from finveritas.shared.schema import (
    FactLedgerEntry,
    FactStatus,
    NormalizedCompanyRecord,
)

MULTI = "multi-period"
DAYS_IN_YEAR = 365.0

_PERIOD_RE = re.compile(r"^(?P<year>\d{4})-(?P<tag>FY|Q[1-4])$")


def period_key(period: str) -> Tuple[int, int]:
    """Chronological sort key. Malformed periods sort last instead of raising."""
    m = _PERIOD_RE.match(str(period).strip())
    if not m:
        return (9999, 9)
    tag = m.group("tag")
    return (int(m.group("year")), 5 if tag == "FY" else int(tag[1:]))


def series(record: NormalizedCompanyRecord, field: str) -> Dict[str, float]:
    """{period: value} for a record field, dropping NaN/inf."""
    out: Dict[str, float] = {}
    for p in getattr(record, field, None) or []:
        if p.value is not None and math.isfinite(p.value):
            out[p.period] = float(p.value)
    return out


def common_periods(record: NormalizedCompanyRecord, fields: Sequence[str]) -> List[str]:
    """Periods where every field has a value, oldest first."""
    if not fields:
        return []
    maps = [series(record, f) for f in fields]
    common = set(maps[0])
    for m in maps[1:]:
        common &= set(m)
    return sorted(common, key=period_key)


def aligned(record: NormalizedCompanyRecord, field: str, periods: Sequence[str]) -> List[float]:
    m = series(record, field)
    return [m[p] for p in periods]


def yoy_pct(values: Sequence[float]) -> List[Optional[float]]:
    """[None, g1, g2, ...] percent change vs the prior period."""
    out: List[Optional[float]] = [None]
    for i in range(1, len(values)):
        prev = values[i - 1]
        out.append(None if prev == 0 else (values[i] - prev) / abs(prev) * 100.0)
    return out


def cagr_pct(first: float, last: float, intervals: int) -> Optional[float]:
    if intervals < 1 or first <= 0 or last <= 0:
        return None
    return ((last / first) ** (1.0 / intervals) - 1.0) * 100.0


def trend_direction(values: Sequence[float]) -> str:
    """increasing / declining / stable from the OLS slope, normalised by mean magnitude (1% per period)."""
    n = len(values)
    if n < 2:
        return "stable"
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    den = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, values)) / den if den else 0.0
    scale = (sum(abs(v) for v in values) / n) or 1.0
    norm = slope / scale
    if norm > 0.01:
        return "increasing"
    if norm < -0.01:
        return "declining"
    return "stable"


def mean(values: Sequence[float]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def stdev(values: Sequence[float]) -> Optional[float]:
    """Population standard deviation (matches the DeterminX anomaly engine)."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))


def latest_period(record: NormalizedCompanyRecord, field: str) -> Optional[str]:
    m = series(record, field)
    return max(m, key=period_key) if m else None


# ---------------------------------------------------------------------------
# Entry builders
# ---------------------------------------------------------------------------

def entry(
    metric: str,
    name: str,
    category: str,
    value: "float | str",
    unit: str,
    period: Optional[str],
    formula: str,
    inputs: Sequence[str] = (),
    *,
    status: FactStatus = FactStatus.VALID,
    notes: Optional[str] = None,
) -> FactLedgerEntry:
    if isinstance(value, float):
        value = round(value, 4)
    return FactLedgerEntry(
        metric=metric, display_name=name, category=category, value=value, unit=unit,
        period=period, formula=formula, inputs_used=list(inputs), status=status, notes=notes,
    )


def unavailable(
    metric: str,
    name: str,
    category: str,
    reason: str,
    formula: Optional[str] = None,
    *,
    status: FactStatus = FactStatus.INSUFFICIENT_DATA,
) -> FactLedgerEntry:
    """A metric we could not produce, with the reason. Never a guess."""
    return FactLedgerEntry(
        metric=metric, display_name=name, category=category, value=None, unit="",
        period=None, formula=formula, status=status, notes=reason,
    )


def requires_document(metric: str, name: str, category: str, reason: str,
                      formula: Optional[str] = None) -> FactLedgerEntry:
    return unavailable(metric, name, category, reason, formula,
                       status=FactStatus.REQUIRES_ADDITIONAL_DOCUMENT)


def requires_external(metric: str, name: str, category: str, reason: str,
                      formula: Optional[str] = None) -> FactLedgerEntry:
    return unavailable(metric, name, category, reason, formula,
                       status=FactStatus.REQUIRES_EXTERNAL_DATA)


def latest_point(values: Dict[str, float]) -> Optional[Tuple[str, float]]:
    """(period, value) for the newest period in a {period: value} map."""
    if not values:
        return None
    p = max(values, key=period_key)
    return p, values[p]


def by_metric(entries: Sequence[FactLedgerEntry], metric: str) -> Optional[FactLedgerEntry]:
    for e in entries:
        if e.metric == metric and e.value is not None:
            return e
    return None
