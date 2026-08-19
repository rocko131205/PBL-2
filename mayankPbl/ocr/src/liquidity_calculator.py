"""Liquidity Calculator (cash-flow proxy)

This service consumes OCR-produced Bloomberg financial statement JSON files from
this repository's `output/` directory. It computes deterministic liquidity and
funding-stability indicators using Python (pandas/numpy).

Hard constraints:
- All numbers are computed in Python.
- Pure deterministic service, no LLM integration.
"""

from __future__ import annotations

import json
import os
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

Trend = Literal["increasing", "declining", "stable"]
RiskFlag = Literal["low", "moderate", "high"]


# ------------------------------
# IO
# ------------------------------

def load_json(path: str | Path) -> dict[str, Any]:
    """Load one OCR output JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"JSON not found: {p}")

    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {p}") from e

    if not isinstance(obj, dict):
        raise ValueError(f"Expected top-level JSON object in {p}")

    return obj


# ------------------------------
# Period handling
# ------------------------------

_PERIOD_RE = re.compile(r"^(?P<year>\d{4})-(?P<tag>FY|Q[1-4])$")


def _period_sort_key(period: str) -> tuple[int, int]:
    """Sort key for 'YYYY-FY' / 'YYYY-QN' periods."""
    m = _PERIOD_RE.match(period.strip())
    if not m:
        raise ValueError(
            f"Unsupported period format: {period!r} (expected 'YYYY-FY' or 'YYYY-QN')"
        )
    year = int(m.group("year"))
    tag = m.group("tag")
    if tag == "FY":
        return year, 5
    return year, int(tag[1:])


def _to_series_map(items: Any, field_name: str) -> dict[str, float]:
    """Convert a time_series[field] array into {period -> value}, dropping nulls."""
    if items is None:
        return {}
    if not isinstance(items, list):
        raise ValueError(f"Expected time_series.{field_name} to be a list")

    out: dict[str, float] = {}
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        p = it.get("period")
        v = it.get("value")
        if not isinstance(p, str) or not p.strip():
            continue
        if v is None:
            continue
        try:
            vf = float(v)
        except (TypeError, ValueError):
            continue
        if np.isnan(vf):
            continue
        out[p.strip()] = vf

    return out


# ------------------------------
# Extraction + validation
# ------------------------------


def extract_liquidity_metrics(payload: dict[str, Any]) -> tuple[str, pd.DataFrame]:
    """Extract required balance-sheet series and return a cleaned DataFrame.

    Required fields (for deterministic indicators):
    - current_assets
    - current_liabilities
    - total_assets
    - total_liabilities
    - equity

    Validation:
    - After dropping nulls and aligning periods, require at least 4 periods.
    - Ensure chronological ordering.
    """
    entity = payload.get("entity") or {}
    entity_id = str(entity.get("entity_id") or "UNKNOWN")

    ts = payload.get("time_series")
    if not isinstance(ts, dict):
        raise ValueError("Missing or invalid 'time_series' in JSON")

    ca = _to_series_map(ts.get("current_assets"), "current_assets")
    cl = _to_series_map(ts.get("current_liabilities"), "current_liabilities")
    ta = _to_series_map(ts.get("total_assets"), "total_assets")
    tl = _to_series_map(ts.get("total_liabilities"), "total_liabilities")
    eq = _to_series_map(ts.get("equity"), "equity")

    # Align on common periods.
    common = set(ca) & set(cl) & set(ta) & set(tl) & set(eq)
    if len(common) < 4:
        raise ValueError(
            "Need at least 4 periods with all required fields present "
            f"(current_assets/current_liabilities/total_assets/total_liabilities/equity). Got {len(common)}"
        )

    periods = sorted(common, key=_period_sort_key)

    df = pd.DataFrame(
        {
            "period": periods,
            "current_assets": [ca[p] for p in periods],
            "current_liabilities": [cl[p] for p in periods],
            "total_assets": [ta[p] for p in periods],
            "total_liabilities": [tl[p] for p in periods],
            "equity": [eq[p] for p in periods],
        }
    )

    # current_assets, current_liabilities, total_assets, total_liabilities must
    # always be positive by accounting convention — reject if negative (data error).
    # Equity CAN be negative (stockholders' deficit in leveraged companies) — allow it.
    for col in ["current_assets", "current_liabilities", "total_assets", "total_liabilities"]:
        if (df[col] < 0).any():
            bad = df.loc[df[col] < 0, ["period", col]].to_dict("records")
            raise ValueError(
                f"Negative values for '{col}' suggest a data ingestion error: {bad}. "
                f"'{col}' must always be positive."
            )

    if (df["equity"] < 0).any():
        import warnings
        warnings.warn(
            "Negative equity (stockholders' deficit) detected — extreme leverage risk signal.",
            RuntimeWarning,
        )

    # Chronological ordering check is implicit in the sorted periods above.
    provided = df["period"].tolist()
    expected = sorted(provided, key=_period_sort_key)
    if provided != expected:
        raise ValueError("Periods are not in chronological order")

    return entity_id, df


# ------------------------------
# Deterministic indicators
# ------------------------------


@dataclass(frozen=True)
class LiquidityIndicators:
    avg_current_ratio: float
    working_capital_trend: Trend
    liquidity_volatility: float
    asset_growth_rate: float
    liability_growth_rate: float
    equity_growth_rate: float
    liquidity_risk_flag: RiskFlag

    def to_dict(self) -> dict[str, Any]:
        return {
            "avg_current_ratio": float(self.avg_current_ratio),
            "working_capital_trend": self.working_capital_trend,
            "liquidity_volatility": float(self.liquidity_volatility),
            "asset_growth_rate": float(self.asset_growth_rate),
            "liability_growth_rate": float(self.liability_growth_rate),
            "equity_growth_rate": float(self.equity_growth_rate),
            "liquidity_risk_flag": self.liquidity_risk_flag,
        }


def _trend_from_slope(*, slope: float, scale: float) -> Trend:
    if scale == 0:
        return "stable"

    norm = slope / scale
    if norm > 0.01:
        return "increasing"
    if norm < -0.01:
        return "declining"
    return "stable"


def _avg_yoy_growth_pct(series: pd.Series) -> float:
    growth = series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if growth.empty:
        raise ValueError("Insufficient data to compute YoY growth")
    return float(growth.mean() * 100.0)


def compute_liquidity_indicators(df: pd.DataFrame) -> dict[str, Any]:
    """Compute deterministic liquidity indicators from aligned balance-sheet data."""

    work = df.copy()

    # Current ratio
    if (work["current_liabilities"] == 0).any():
        bad = work.loc[work["current_liabilities"] == 0, "period"].tolist()
        raise ValueError(f"current_liabilities is 0 for periods {bad}; cannot compute current ratio")

    work["current_ratio"] = work["current_assets"] / work["current_liabilities"]
    avg_current_ratio = float(work["current_ratio"].mean())

    # Current-ratio trend (used for risk scoring; not exposed as an output metric)
    x = np.arange(len(work), dtype=float)
    cr = work["current_ratio"].to_numpy(dtype=float)
    cr_slope = float(np.polyfit(x, cr, deg=1)[0])
    current_ratio_trend = _trend_from_slope(slope=cr_slope, scale=float(np.mean(np.abs(cr))) or 1.0)

    # Working capital
    work["working_capital"] = work["current_assets"] - work["current_liabilities"]
    liquidity_volatility = float(work["working_capital"].std(ddof=0))

    # Working capital trend via linear regression slope
    wc = work["working_capital"].to_numpy(dtype=float)
    wc_slope = float(np.polyfit(x, wc, deg=1)[0])
    working_capital_trend = _trend_from_slope(
        slope=wc_slope,
        scale=float(np.mean(np.abs(wc))) or 1.0,
    )

    # Growth rates (average YoY %)
    asset_growth_rate = _avg_yoy_growth_pct(work["total_assets"])
    liability_growth_rate = _avg_yoy_growth_pct(work["total_liabilities"])
    equity_growth_rate = _avg_yoy_growth_pct(work["equity"])

    # Accounting identity warning: total_assets ≈ total_liabilities + equity
    # We only warn; OCR/mapping noise is expected.
    identity_diff = work["total_assets"] - (work["total_liabilities"] + work["equity"])
    if not np.allclose(identity_diff.to_numpy(dtype=float), 0.0, rtol=0.01, atol=1e-6):
        worst = float(np.max(np.abs(identity_diff)))
        warnings.warn(
            "Accounting identity mismatch detected (total_assets != total_liabilities + equity) "
            f"for at least one period. Max absolute diff={worst}.",
            RuntimeWarning,
        )

    liquidity_risk_flag = classify_liquidity_risk(
        avg_current_ratio=avg_current_ratio,
        current_ratio_trend=current_ratio_trend,
        working_capital_trend=working_capital_trend,
        working_capital_volatility=liquidity_volatility,
        working_capital_mean=float(work["working_capital"].mean()),
        asset_growth_rate=asset_growth_rate,
        liability_growth_rate=liability_growth_rate,
    )

    indicators = LiquidityIndicators(
        avg_current_ratio=avg_current_ratio,
        working_capital_trend=working_capital_trend,
        liquidity_volatility=liquidity_volatility,
        asset_growth_rate=asset_growth_rate,
        liability_growth_rate=liability_growth_rate,
        equity_growth_rate=equity_growth_rate,
        liquidity_risk_flag=liquidity_risk_flag,
    )

    return {"metrics": indicators.to_dict()}


def classify_liquidity_risk(
    *,
    avg_current_ratio: float,
    current_ratio_trend: Trend,
    working_capital_trend: Trend,
    working_capital_volatility: float,
    working_capital_mean: float,
    asset_growth_rate: float,
    liability_growth_rate: float,
) -> RiskFlag:
    """Deterministic risk heuristic.

    Output is a qualitative flag only.

    Signals used:
    - Average current ratio level.
    - Trend of current ratio and working capital.
    - Liability growth relative to asset growth.
    - Working capital volatility (normalized by mean magnitude).
    """

    score = 0

    # Current ratio signal
    if avg_current_ratio < 1.0:
        score += 3
    elif avg_current_ratio < 1.5:
        score += 1

    # Trend signals
    if current_ratio_trend == "declining":
        score += 1
    if working_capital_trend == "declining":
        score += 1

    # Relative growth signal
    if liability_growth_rate > asset_growth_rate + 2.0:
        score += 2
    elif liability_growth_rate > asset_growth_rate:
        score += 1

    # Volatility signal: coefficient of variation proxy
    denom = max(1.0, float(abs(working_capital_mean)))
    cv = float(working_capital_volatility) / denom
    if cv > 0.5:
        score += 1

    if score >= 4:
        return "high"
    if score >= 2:
        return "moderate"
    return "low"


# ------------------------------
# Output builder / orchestration
# ------------------------------


def write_agent_output(*, payload: dict[str, Any], output_dir: str | Path) -> Path:
    """Persist the agent output to a JSON file.

    The output is written to:
        {output_dir}/{sanitized_entity}_liquidity.json

    Returns the written path.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entity = str(payload.get("entity") or "UNKNOWN")
    safe = "".join(c if c.isalnum() or c in ("-", "_", " ") else "_" for c in entity).strip()
    safe = safe.replace(" ", "_") or "UNKNOWN"

    out_path = out_dir / f"{safe}_liquidity.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


def calculate_liquidity_metrics(json_path: str | Path) -> dict[str, Any]:
    payload = load_json(json_path)
    entity, df = extract_liquidity_metrics(payload)
    computed = compute_liquidity_indicators(df)
    metrics = computed["metrics"]

    return {"entity": entity, "metrics": metrics}


def _main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Liquidity Calculator (deterministic metrics only)")
    ap.add_argument("--json", required=True, help="Path to an OCR output JSON")
    ap.add_argument(
        "--out-dir",
        default="liquidity_output",
        help="Directory to write the output JSON (default: liquidity_output/)",
    )
    args = ap.parse_args()

    out = calculate_liquidity_metrics(json_path=args.json)
    written = write_agent_output(payload=out, output_dir=args.out_dir)

    # Keep stdout useful for demos, but also persist to a file.
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nWrote: {written}")


if __name__ == "__main__":
    _main()
