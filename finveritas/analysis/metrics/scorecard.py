"""Credit scorecard (V3, Phase 3).

Turns the scattered ratios into ONE defensible answer: a credit grade + an
approximate probability-of-default (PD) band, with a transparent breakdown of
which factors helped or hurt.

Key design choices:
- **Industry-aware.** The same margin or leverage means different things for a
  SaaS firm vs a bank vs a manufacturer. Thresholds adjust by industry profile.
  (This fixes the old "SaaS thresholds applied to everyone" bug.)
- **Transparent.** Every factor shows its value, 0-100 score, weight, and
  contribution. Nothing is a black box.
- **Honest about missing data.** Weights are renormalized over the factors we
  can actually compute, and we report how much of the scorecard was covered.
- Pure deterministic math — no LLM.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from finveritas.shared.schema import NormalizedCompanyRecord


# -------------------------------------------------------------------------
# Result models
# -------------------------------------------------------------------------

class ScoreFactor(BaseModel):
    key: str
    name: str
    bucket: str
    value: Optional[float]
    unit: str
    score: Optional[float]          # 0-100, None if not computable
    weight: float                   # nominal weight (of 100)
    contribution: Optional[float]   # score * weight / 100
    note: str = ""
    status: str = "missing"         # strong | ok | weak | missing


class CreditScorecard(BaseModel):
    entity_id: str
    industry: Optional[str] = None
    industry_profile: str = "general"
    composite_score: Optional[float] = None   # 0-100
    grade: str = "NR"
    grade_label: str = "Not Rated"
    pd_band: str = "n/a"
    covered_weight: float = 0.0               # 0-1, share of weight with data
    buckets: Dict[str, Optional[float]] = Field(default_factory=dict)
    factors: List[ScoreFactor] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


# -------------------------------------------------------------------------
# Scoring helpers
# -------------------------------------------------------------------------

def _interp(value: float, anchors: List[Tuple[float, float]]) -> float:
    """Piecewise-linear score. `anchors` = [(threshold, score), ...] ascending by
    threshold. Scores may increase (higher-better) or decrease (lower-better) —
    the anchor pairs encode the direction. Clamped outside the anchor range."""
    if value <= anchors[0][0]:
        return anchors[0][1]
    if value >= anchors[-1][0]:
        return anchors[-1][1]
    for (t0, s0), (t1, s1) in zip(anchors, anchors[1:]):
        if t0 <= value <= t1:
            if t1 == t0:
                return s1
            frac = (value - t0) / (t1 - t0)
            return s0 + frac * (s1 - s0)
    return anchors[-1][1]


def _status(score: Optional[float]) -> str:
    if score is None:
        return "missing"
    if score >= 70:
        return "strong"
    if score >= 45:
        return "ok"
    return "weak"


# -------------------------------------------------------------------------
# Industry profiles — anchors that vary by sector
# -------------------------------------------------------------------------

# Universal anchors (industry-independent)
_UNIVERSAL = {
    "dscr":             [(0.5, 0), (1.0, 30), (1.25, 50), (1.5, 70), (2.0, 90), (3.0, 100)],
    "interest_coverage":[(0.5, 0), (1.0, 20), (2.0, 50), (4.0, 75), (8.0, 95), (12.0, 100)],
    "current_ratio":    [(0.5, 0), (1.0, 40), (1.5, 70), (2.0, 90), (3.0, 100)],
    "roe":              [(-20, 0), (0, 40), (10, 60), (20, 85), (30, 100)],
    "revenue_growth":   [(-20, 5), (-10, 20), (0, 45), (10, 70), (25, 95), (40, 100)],
    "revenue_stability":[(0, 100), (10, 80), (25, 60), (50, 35), (100, 10)],  # lower volatility better
}

# Industry-specific anchors override the general set
_PROFILES: Dict[str, Dict[str, List[Tuple[float, float]]]] = {
    "general": {
        "operating_margin":  [(-5, 20), (0, 40), (8, 60), (15, 80), (25, 100)],
        "net_margin":        [(-10, 15), (0, 40), (5, 65), (12, 90), (20, 100)],
        "debt_to_equity":    [(0, 100), (0.5, 85), (1.0, 65), (2.0, 40), (3.0, 20), (5.0, 0)],
        "net_debt_to_ebitda":[(0, 100), (1, 90), (2, 75), (3, 55), (4, 35), (6, 10)],
    },
    "software_saas": {
        "operating_margin":  [(-10, 25), (0, 45), (10, 65), (20, 85), (30, 100)],
        "net_margin":        [(-15, 20), (0, 45), (8, 70), (18, 95), (25, 100)],
        "debt_to_equity":    [(0, 100), (0.3, 85), (0.7, 65), (1.5, 40), (3.0, 15)],
        "net_debt_to_ebitda":[(0, 100), (1, 88), (2.5, 65), (4, 40), (6, 10)],
    },
    "manufacturing": {
        "operating_margin":  [(0, 35), (5, 55), (10, 75), (18, 100)],
        "net_margin":        [(-5, 25), (0, 45), (4, 65), (9, 90), (15, 100)],
        "debt_to_equity":    [(0, 100), (1.0, 80), (2.0, 55), (3.5, 30), (5.0, 10)],
        "net_debt_to_ebitda":[(0, 100), (1.5, 85), (3, 60), (4.5, 35), (6, 10)],
    },
    "retail": {
        "operating_margin":  [(0, 40), (3, 60), (6, 80), (10, 100)],
        "net_margin":        [(-3, 25), (0, 45), (2, 65), (5, 90), (8, 100)],
        "debt_to_equity":    [(0, 100), (0.7, 82), (1.5, 60), (2.5, 35), (4.0, 10)],
        "net_debt_to_ebitda":[(0, 100), (1.5, 85), (3, 60), (4.5, 35), (6, 10)],
    },
    "financial": {  # banks/NBFCs carry structurally high leverage — heavily relaxed
        "operating_margin":  [(0, 40), (10, 60), (25, 85), (40, 100)],
        "net_margin":        [(0, 40), (8, 60), (18, 85), (30, 100)],
        "debt_to_equity":    [(0, 100), (3, 85), (6, 65), (9, 45), (12, 25)],
        "net_debt_to_ebitda":[(0, 100), (3, 85), (6, 60), (9, 35), (12, 10)],
    },
}


def resolve_profile(industry: Optional[str]) -> str:
    """Map a free-text industry to a scorecard profile name."""
    if not industry:
        return "general"
    s = industry.lower()
    if any(k in s for k in ("software", "saas", "technology", "internet", "cloud")):
        return "software_saas"
    if any(k in s for k in ("bank", "financial", "insurance", "nbfc", "lending")):
        return "financial"
    if any(k in s for k in ("manufactur", "industrial", "auto", "chemical", "materials", "energy")):
        return "manufacturing"
    if any(k in s for k in ("retail", "consumer", "commerce", "apparel", "food")):
        return "retail"
    return "general"


def _anchors(profile: str, key: str) -> Optional[List[Tuple[float, float]]]:
    if key in _UNIVERSAL:
        return _UNIVERSAL[key]
    return _PROFILES.get(profile, _PROFILES["general"]).get(key)


# -------------------------------------------------------------------------
# Factor extraction from the record
# -------------------------------------------------------------------------

def _pct(n: Optional[float], d: Optional[float]) -> Optional[float]:
    if n is None or d is None or abs(d) < 1e-9:
        return None
    return n / d * 100.0


def _ratio(n: Optional[float], d: Optional[float]) -> Optional[float]:
    if n is None or d is None or abs(d) < 1e-9:
        return None
    return n / d


def _revenue_growth(record: NormalizedCompanyRecord) -> Optional[float]:
    rev = sorted(record.revenue, key=lambda x: x.period)
    if len(rev) < 2 or abs(rev[-2].value) < 1e-9:
        return None
    return (rev[-1].value - rev[-2].value) / abs(rev[-2].value) * 100.0


def _revenue_volatility(record: NormalizedCompanyRecord) -> Optional[float]:
    rev = sorted(record.revenue, key=lambda x: x.period)
    if len(rev) < 3:
        return None
    growths = []
    for a, b in zip(rev, rev[1:]):
        if abs(a.value) > 1e-9:
            growths.append((b.value - a.value) / abs(a.value) * 100.0)
    if len(growths) < 2:
        return None
    mean = sum(growths) / len(growths)
    var = sum((g - mean) ** 2 for g in growths) / len(growths)
    return var ** 0.5


# (bucket, key, name, unit, weight)
_FACTOR_DEFS = [
    ("Repayment capacity", "dscr",              "Min DSCR",            "x", 20),
    ("Repayment capacity", "interest_coverage", "Interest Coverage",   "x", 15),
    ("Leverage",           "debt_to_equity",    "Debt / Equity",       "x", 15),
    ("Leverage",           "net_debt_to_ebitda","Net Debt / EBITDA",   "x", 10),
    ("Liquidity",          "current_ratio",     "Current Ratio",       "x", 15),
    ("Profitability",      "operating_margin",  "Operating Margin",    "%", 8),
    ("Profitability",      "net_margin",        "Net Margin",          "%", 4),
    ("Profitability",      "roe",               "Return on Equity",    "%", 3),
    ("Stability",          "revenue_growth",    "Revenue Growth",      "%", 5),
    ("Stability",          "revenue_stability", "Revenue Stability",   "σ%", 5),
]


def compute_scorecard(
    record: NormalizedCompanyRecord,
    industry: Optional[str] = None,
    min_dscr: Optional[float] = None,
) -> CreditScorecard:
    """Build a credit scorecard for the company.

    min_dscr: the minimum DSCR from the Phase-2 debt-service schedule, if a loan
    was analysed. Without it, the DSCR factor is treated as missing.
    """
    profile = resolve_profile(industry)

    rev = record.latest_value("revenue")
    op_income = record.latest_value("operating_income")
    net_income = record.latest_value("net_income")
    equity = record.latest_value("equity")
    interest = record.latest_value("interest_expense")
    ebitda = record.latest_value("ebitda")
    total_debt = record.latest_value("total_debt") or record.latest_value("total_liabilities")
    cash = record.latest_value("cash_and_equivalents")
    cur_assets = record.latest_value("current_assets")
    cur_liabs = record.latest_value("current_liabilities")

    net_debt = (total_debt - cash) if (total_debt is not None and cash is not None) else total_debt

    values: Dict[str, Optional[float]] = {
        "dscr": min_dscr,
        "interest_coverage": _ratio(op_income, abs(interest) if interest is not None else None),
        "debt_to_equity": _ratio(total_debt, equity),
        "net_debt_to_ebitda": _ratio(net_debt, ebitda),
        "current_ratio": _ratio(cur_assets, cur_liabs),
        "operating_margin": _pct(op_income, rev),
        "net_margin": _pct(net_income, rev),
        "roe": _pct(net_income, equity),
        "revenue_growth": _revenue_growth(record),
        "revenue_stability": _revenue_volatility(record),
    }

    factors: List[ScoreFactor] = []
    for bucket, key, name, unit, weight in _FACTOR_DEFS:
        val = values.get(key)
        anchors = _anchors(profile, key)
        score = _interp(val, anchors) if (val is not None and anchors) else None
        factors.append(ScoreFactor(
            key=key, name=name, bucket=bucket, value=round(val, 2) if val is not None else None,
            unit=unit, score=round(score, 1) if score is not None else None, weight=weight,
            contribution=round(score * weight / 100.0, 2) if score is not None else None,
            status=_status(score),
            note=_factor_note(key, val, unit),
        ))

    scored = [f for f in factors if f.score is not None]
    total_weight_available = sum(f.weight for f in scored)
    covered = total_weight_available / sum(f.weight for f in factors)

    composite = None
    if total_weight_available > 0:
        composite = sum(f.score * f.weight for f in scored) / total_weight_available

    # Bucket-level weighted scores
    buckets: Dict[str, Optional[float]] = {}
    for b in ("Repayment capacity", "Leverage", "Liquidity", "Profitability", "Stability"):
        bf = [f for f in scored if f.bucket == b]
        bw = sum(f.weight for f in bf)
        buckets[b] = round(sum(f.score * f.weight for f in bf) / bw, 1) if bw > 0 else None

    grade, label, pd_band = _grade(composite)

    notes: List[str] = []
    if covered < 0.6:
        notes.append(f"Only {covered*100:.0f}% of scorecard weight had data — grade is indicative; supply more fields.")
    if min_dscr is None:
        notes.append("No loan analysed yet, so debt-service coverage is excluded. Run the Debt Serviceability section for a fuller picture.")
    if profile == "financial":
        notes.append("Banks/financials need a specialised capital-adequacy model; leverage thresholds here are relaxed but not a substitute.")

    return CreditScorecard(
        entity_id=record.entity_id,
        industry=industry,
        industry_profile=profile,
        composite_score=round(composite, 1) if composite is not None else None,
        grade=grade, grade_label=label, pd_band=pd_band,
        covered_weight=round(covered, 3),
        buckets=buckets,
        factors=factors,
        notes=notes,
    )


def _factor_note(key: str, val: Optional[float], unit: str) -> str:
    if val is None:
        return "no data"
    if key == "revenue_stability":
        return f"growth volatility {val:.0f}% (lower is steadier)"
    return f"{val:.2f}{unit}"


def _grade(composite: Optional[float]) -> Tuple[str, str, str]:
    """Map a 0-100 composite to a grade, label, and approximate PD band."""
    if composite is None:
        return "NR", "Not Rated", "n/a"
    if composite >= 85:
        return "AA", "Very low risk", "<0.5%"
    if composite >= 75:
        return "A", "Low risk", "0.5–1%"
    if composite >= 65:
        return "BBB", "Investment grade", "1–3%"
    if composite >= 55:
        return "BB", "Speculative", "3–7%"
    if composite >= 45:
        return "B", "Highly speculative", "7–15%"
    if composite >= 35:
        return "CCC", "Substantial risk", "15–30%"
    return "D", "Distressed", ">30%"
