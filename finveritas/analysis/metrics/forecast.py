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


# ---------------------------------------------------------------------------
# Assumption validation (ported from DeterminX src/forecast)
# ---------------------------------------------------------------------------
# The user states a growth assumption; Python compares it with every reference we
# can actually source (the company's own CAGR and average growth, management
# guidance, a benchmark the user supplies) and decides the verdict. The LLM may
# later explain WHY, but it can never change the verdict.

_OPTIMISTIC_BAND_PP = 5.0   # up to this far above the reference high is OPTIMISTIC, beyond it AGGRESSIVE
_ALIGNED_MARGIN_PP = 1.0    # tolerance around the reference range before any deviation is called

_VALIDATABLE = {"revenue": "revenue", "ebitda": "ebitda", "pat": "net_income"}


class ReferencePoint(BaseModel):
    label: str
    value_pct: float
    source: str


def gather_reference_points(
    record: NormalizedCompanyRecord,
    metric: str = "revenue",
    *,
    guidance_low: Optional[float] = None,
    guidance_high: Optional[float] = None,
    sector_benchmark_pct: Optional[float] = None,
) -> List[ReferencePoint]:
    """Every reference point that really exists. Nothing is invented when a source is missing."""
    from finveritas.analysis.metrics.extended import _util as u

    field = _VALIDATABLE.get(metric)
    refs: List[ReferencePoint] = []
    periods = u.common_periods(record, [field]) if field else []
    if len(periods) >= 2:
        values = u.aligned(record, field, periods)
        cagr = u.cagr_pct(values[0], values[-1], len(values) - 1)
        if cagr is not None:
            refs.append(ReferencePoint(label=f"Historical {metric} CAGR", value_pct=round(cagr, 3),
                                       source="financial_statement"))
        yoy = [g for g in u.yoy_pct(values) if g is not None]
        if yoy:
            refs.append(ReferencePoint(label=f"Historical average YoY {metric} growth",
                                       value_pct=round(sum(yoy) / len(yoy), 3), source="financial_statement"))
    if guidance_low is not None:
        refs.append(ReferencePoint(label="Management guidance (low)", value_pct=float(guidance_low),
                                   source="management_guidance"))
    if guidance_high is not None:
        refs.append(ReferencePoint(label="Management guidance (high)", value_pct=float(guidance_high),
                                   source="management_guidance"))
    if sector_benchmark_pct is not None:
        refs.append(ReferencePoint(label="Sector / peer benchmark (user-supplied)",
                                   value_pct=float(sector_benchmark_pct), source="user_input"))
    return refs


def classify_assumption(user_assumption_pct: float, references: List[ReferencePoint]) -> dict:
    """The ONLY place the verdict is decided: ALIGNED / OPTIMISTIC / AGGRESSIVE / CAUTIOUS /
    OVERLY_CONSERVATIVE, or NO_REFERENCE_DATA when there is nothing to compare against."""
    if not references:
        return {"verdict": "NO_REFERENCE_DATA", "reference_low": None, "reference_high": None, "deviation_pp": None,
                "detail": "No historical, guidance or benchmark reference points were available to validate against."}
    values = [r.value_pct for r in references]
    low, high = min(values), max(values)
    if low - _ALIGNED_MARGIN_PP <= user_assumption_pct <= high + _ALIGNED_MARGIN_PP:
        verdict, deviation = "ALIGNED", 0.0
    elif user_assumption_pct > high:
        deviation = user_assumption_pct - high
        verdict = "OPTIMISTIC" if deviation <= _OPTIMISTIC_BAND_PP else "AGGRESSIVE"
    else:
        deviation = low - user_assumption_pct
        verdict = "CAUTIOUS" if deviation <= _OPTIMISTIC_BAND_PP else "OVERLY_CONSERVATIVE"
    return {
        "verdict": verdict, "reference_low": round(low, 3), "reference_high": round(high, 3),
        "deviation_pp": round(deviation, 3),
        "detail": (f"Assumption {user_assumption_pct:.2f}% vs reference range [{low:.2f}%, {high:.2f}%] "
                   f"built from {len(references)} reference point(s)."),
    }


def project_series(latest_value: float, latest_period: str, growth_rate_pct: float, periods_ahead: int) -> List[dict]:
    """Pure compounding at the user's own rate. Deterministic; no LLM."""
    out, value = [], latest_value
    labels = _next_periods(latest_period, periods_ahead)
    for label in labels:
        value *= 1 + growth_rate_pct / 100.0
        out.append({"period": label, "value": round(value, 4)})
    return out


def growth_drivers(record: NormalizedCompanyRecord, metric: str = "revenue") -> List[str]:
    """Deterministic observations about the historical growth pattern: the ONLY "why" material
    the narrator is allowed to cite."""
    from finveritas.analysis.metrics.extended import _util as u

    field = _VALIDATABLE.get(metric)
    periods = u.common_periods(record, [field]) if field else []
    values = u.aligned(record, field, periods) if periods else []
    drivers: List[str] = []
    yoy = [g for g in u.yoy_pct(values) if g is not None]
    if len(yoy) >= 3:
        recent, earlier = yoy[-2:], yoy[:-2]
        r_avg, e_avg = sum(recent) / len(recent), sum(earlier) / len(earlier)
        if r_avg < e_avg - 1.0:
            drivers.append(f"historical growth has been decelerating (recent avg {r_avg:.2f}% vs earlier avg {e_avg:.2f}%)")
        elif r_avg > e_avg + 1.0:
            drivers.append(f"historical growth has been accelerating (recent avg {r_avg:.2f}% vs earlier avg {e_avg:.2f}%)")
        else:
            drivers.append(f"historical growth has been broadly stable (~{r_avg:.2f}% recently)")
    if len(values) >= 3:
        drivers.append(f"the long-run trend classification is '{u.trend_direction(values)}'")
    return drivers
