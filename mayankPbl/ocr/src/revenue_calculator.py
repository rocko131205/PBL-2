"""Revenue Calculator

Loads an OCR-produced JSON (from this repo's `output/` folder), extracts the
revenue time series, and computes deterministic metrics.

Design constraints:
- All numeric computations happen in Python (pandas/numpy).
- This is a pure deterministic service, no LLM integration.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

TrendDirection = Literal["increasing", "declining", "stable"]


# ------------------------------
# IO
# ------------------------------

def load_json(path: str | Path) -> dict[str, Any]:
    """Load a single OCR output JSON file.

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if JSON is malformed or not a dict.
    """
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
# Revenue parsing + validation
# ------------------------------

_PERIOD_RE = re.compile(r"^(?P<year>\d{4})-(?P<tag>FY|Q[1-4])$")


def _period_sort_key(period: str) -> tuple[int, int]:
    """Sortable key for periods like '2024-FY' or '2024-Q2'."""
    m = _PERIOD_RE.match(period.strip())
    if not m:
        raise ValueError(
            f"Unsupported period format: {period!r} (expected 'YYYY-FY' or 'YYYY-QN')"
        )

    year = int(m.group("year"))
    tag = m.group("tag")
    if tag == "FY":
        # Ensure FY sorts after all quarters within the same year if ever mixed.
        return year, 5

    q = int(tag[1:])
    return year, q


def _extract_revenue_series(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    entity = payload.get("entity") or {}
    entity_id = entity.get("entity_id") or "UNKNOWN"

    ts = payload.get("time_series")
    if not isinstance(ts, dict):
        raise ValueError("Missing or invalid 'time_series' in JSON")

    revenue = ts.get("revenue")
    if revenue is None:
        raise ValueError("Missing 'time_series.revenue' in JSON")
    if not isinstance(revenue, list):
        raise ValueError("Expected 'time_series.revenue' to be a list")

    return str(entity_id), revenue


def _validate_and_frame(revenue: list[dict[str, Any]]) -> pd.DataFrame:
    """Validate revenue records and return a canonical DataFrame.

    Validation requirements:
    - Minimum 4 periods
    - No null values
    - No negative values
    - Chronological ordering (as provided)
    """
    if len(revenue) < 4:
        raise ValueError(f"Need at least 4 revenue periods; got {len(revenue)}")

    rows: list[dict[str, Any]] = []
    for i, item in enumerate(revenue):
        if not isinstance(item, dict):
            raise ValueError(f"Revenue item at index {i} is not an object")

        period = item.get("period")
        value = item.get("value")

        if period is None or not isinstance(period, str) or not period.strip():
            raise ValueError(f"Revenue item at index {i} missing valid 'period'")

        # Disallow nulls/NaNs.
        if value is None:
            raise ValueError(f"Revenue value is null for period {period}")
        try:
            value_f = float(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Revenue value is not numeric for period {period}: {value!r}") from e

        if np.isnan(value_f):
            raise ValueError(f"Revenue value is NaN for period {period}")
        if value_f < 0:
            raise ValueError(f"Revenue value is negative for period {period}: {value_f}")

        rows.append({"period": period.strip(), "revenue": value_f})

    df = pd.DataFrame(rows)

    # Validate unique periods.
    if df["period"].duplicated().any():
        dups = df[df["period"].duplicated()]["period"].tolist()
        raise ValueError(f"Duplicate revenue periods found: {dups}")

    # Validate chronological ordering (as provided) using the sortable key.
    provided_periods = df["period"].tolist()
    sorted_periods = sorted(provided_periods, key=_period_sort_key)
    if provided_periods != sorted_periods:
        raise ValueError(
            "Revenue periods are not in chronological order. "
            f"Provided={provided_periods} Sorted={sorted_periods}"
        )

    # Attach sortable keys for downstream use.
    df["_year"], df["_sub" ] = zip(*(_period_sort_key(p) for p in df["period"]))

    return df


# ------------------------------
# Metrics
# ------------------------------


@dataclass(frozen=True)
class RevenueMetrics:
    avg_growth: float
    cagr: float
    volatility: float
    positive_growth_ratio: float
    trend_direction: TrendDirection

    def to_dict(self) -> dict[str, Any]:
        return {
            "avg_growth": float(self.avg_growth),
            "cagr": float(self.cagr),
            "volatility": float(self.volatility),
            "positive_growth_ratio": float(self.positive_growth_ratio),
            "trend_direction": self.trend_direction,
        }


def compute_metrics(df: pd.DataFrame) -> dict[str, Any]:
    """Compute deterministic revenue metrics.

    Returns a dict containing:
    - metrics: RevenueMetrics (as dict)
    - intermediate: series and regression info (internal use for trend classification / prompting)

    Notes:
    - YoY growth is computed as pct_change on revenue and expressed in percent.
    - Volatility is std-dev of YoY growth (percentage points).
    - Linear regression slope is computed on raw revenue vs integer time index.
    """
    series = df[["period", "revenue"]].copy()

    # YoY growth in percent (first is NaN)
    series["yoy_growth_pct"] = series["revenue"].pct_change() * 100.0

    growth = series["yoy_growth_pct"].replace([np.inf, -np.inf], np.nan).dropna()
    if growth.empty:
        raise ValueError("Insufficient valid growth observations to compute growth metrics")

    avg_growth = float(growth.mean())
    volatility = float(growth.std(ddof=0))

    positive_growth_ratio = float((growth > 0).mean())

    first = float(series["revenue"].iloc[0])
    last = float(series["revenue"].iloc[-1])
    n_periods = int(series.shape[0])
    years = n_periods - 1

    if years < 1:
        raise ValueError("Need at least 2 revenue points to compute CAGR")
    if first <= 0:
        raise ValueError("Cannot compute CAGR when the first revenue value is <= 0")

    cagr = float(((last / first) ** (1.0 / years) - 1.0) * 100.0)

    # Linear regression slope (revenue units per period)
    x = np.arange(n_periods, dtype=float)
    y = series["revenue"].to_numpy(dtype=float)
    slope = float(np.polyfit(x, y, deg=1)[0])

    trend = classify_trend(slope=slope, revenue_mean=float(np.mean(y)))

    metrics = RevenueMetrics(
        avg_growth=avg_growth,
        cagr=cagr,
        volatility=volatility,
        positive_growth_ratio=positive_growth_ratio,
        trend_direction=trend,
    )

    return {
        "metrics": metrics.to_dict(),
        "intermediate": {
            "periods": series["period"].tolist(),
            "revenue": [float(v) for v in series["revenue"].tolist()],
            "yoy_growth_pct": [None if pd.isna(v) else float(v) for v in series["yoy_growth_pct"].tolist()],
            "regression_slope": slope,
        },
    }


def classify_trend(*, slope: float, revenue_mean: float) -> TrendDirection:
    """Classify trend direction using a normalized slope threshold.

    We normalize slope by mean revenue to reduce sensitivity to company scale.

    Thresholds are intentionally simple/deterministic (production-friendly).
    """
    if revenue_mean == 0:
        return "stable"

    normalized = slope / revenue_mean  # per-period, fraction of mean

    # 1% of mean per period threshold.
    if normalized > 0.01:
        return "increasing"
    if normalized < -0.01:
        return "declining"
    return "stable"


# ------------------------------
# Orchestration
# ------------------------------

def calculate_revenue_metrics(json_path: str | Path) -> dict[str, Any]:
    """Load JSON, validate, and compute deterministic revenue metrics."""

    payload = load_json(json_path)
    entity, revenue_series = _extract_revenue_series(payload)
    df = _validate_and_frame(revenue_series)

    computed = compute_metrics(df)
    metrics = computed["metrics"]

    return {
        "entity": entity,
        "metrics": metrics,
    }


def _main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Revenue Calculator (deterministic metrics only)")
    ap.add_argument(
        "--json",
        required=True,
        help="Path to an OCR output JSON (e.g. output/Company.json)",
    )
    args = ap.parse_args()

    out = calculate_revenue_metrics(args.json)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()
