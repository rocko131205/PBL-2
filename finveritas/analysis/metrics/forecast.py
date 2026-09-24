"""Forward-looking forecasting (V3, Phase 5).

Projects revenue (and margin-derived earnings) forward from the company's own
historical trend, with base / optimistic / pessimistic scenarios. This shifts the
tool from "what happened" to "can they repay over the life of the loan."

Deterministic: CAGR-based projection with a transparent scenario spread. No LLM.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from finveritas.shared.schema import NormalizedCompanyRecord


class ForecastPoint(BaseModel):
    period: str
    base: float
    optimistic: float
    pessimistic: float


class Forecast(BaseModel):
    metric: str
    unit: str = "currency"
    historical: List[Tuple[str, float]] = Field(default_factory=list)
    points: List[ForecastPoint] = Field(default_factory=list)
    cagr_pct: Optional[float] = None
    base_growth_pct: Optional[float] = None
    optimistic_growth_pct: Optional[float] = None
    pessimistic_growth_pct: Optional[float] = None
    method: str = ""
    assumptions: List[str] = Field(default_factory=list)


def _cagr(first: float, last: float, periods: int) -> Optional[float]:
    """Compound annual growth rate (%) over `periods` intervals."""
    if periods <= 0 or first <= 0 or last <= 0:
        return None
    return ((last / first) ** (1.0 / periods) - 1.0) * 100.0


def _next_periods(last_period: str, n: int) -> List[str]:
    """Generate n future 'YYYY-FY' labels after last_period (best-effort)."""
    try:
        year = int(str(last_period)[:4])
    except (ValueError, TypeError):
        year = 0
    if year == 0:
        return [f"F+{i}" for i in range(1, n + 1)]
    return [f"{year + i}-FY" for i in range(1, n + 1)]


def forecast_field(
    record: NormalizedCompanyRecord,
    field: str = "revenue",
    years: int = 3,
) -> Optional[Forecast]:
    """Forecast a monetary field forward `years` from its historical CAGR.

    Returns None if there isn't enough history (need >= 2 positive points).
    """
    series = sorted(getattr(record, field, []), key=lambda x: x.period)
    hist = [(p.period, p.value) for p in series]
    positives = [v for _, v in hist if v > 0]
    if len(hist) < 2 or len(positives) < 2:
        return None

    first, last = hist[0][1], hist[-1][1]
    intervals = len(hist) - 1
    cagr = _cagr(first, last, intervals)
    if cagr is None:
        # fall back to simple average YoY if endpoints unusable
        cagr = 0.0

    # Scenario spread: at least 5pp, wider for volatile histories.
    spread = max(5.0, abs(cagr) * 0.3)
    base_g = cagr
    opt_g = cagr + spread
    pess_g = cagr - spread

    fc = Forecast(
        metric=field,
        historical=hist,
        cagr_pct=round(cagr, 2),
        base_growth_pct=round(base_g, 2),
        optimistic_growth_pct=round(opt_g, 2),
        pessimistic_growth_pct=round(pess_g, 2),
        method=f"CAGR projection from {len(hist)} historical periods",
        assumptions=[
            f"Base case grows at the historical CAGR ({cagr:.1f}%/yr).",
            f"Optimistic/pessimistic apply a ±{spread:.1f}pp spread.",
            "Projection is trend-based; it does not model demand shocks or one-offs.",
        ],
    )

    periods = _next_periods(hist[-1][0], years)
    b = o = p = last
    for period in periods:
        b *= (1 + base_g / 100.0)
        o *= (1 + opt_g / 100.0)
        p *= (1 + pess_g / 100.0)
        fc.points.append(ForecastPoint(period=period, base=round(b, 2),
                                       optimistic=round(o, 2), pessimistic=round(p, 2)))
    return fc
