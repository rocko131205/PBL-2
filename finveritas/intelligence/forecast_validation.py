"""Forecast assumption validation.

    user assumption -> reference points -> Python comparison -> verdict -> projection -> LLM explains why

The verdict comes from ``forecast.classify_assumption`` and the projection from
``forecast.project_series``; the LLM only narrates the already-decided result and cannot move
either. Ported from DeterminX ``src/forecast``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from finveritas.analysis.metrics import extended
from finveritas.analysis.metrics.forecast import (
    classify_assumption,
    gather_reference_points,
    growth_drivers,
    project_series,
)
from finveritas.intelligence import external
from finveritas.intelligence.narrate import narrate
from finveritas.shared.schema import NormalizedCompanyRecord

FIELDS = {"revenue": "revenue", "ebitda": "ebitda", "pat": "net_income"}
LABELS = {"revenue": "Revenue", "ebitda": "EBITDA", "pat": "Net profit (PAT)"}

_ROLE = (
    "You explain whether a user's growth assumption is realistic. The verdict "
    "(ALIGNED / OPTIMISTIC / AGGRESSIVE / CAUTIOUS / OVERLY_CONSERVATIVE) and the projected figures are final. "
    "Cite only the reference points and growth drivers provided; do not invent drivers. Write 4-7 concise, "
    "professional sentences, ending with one sentence on whether the forecast should be read as a base, "
    "optimistic or conservative scenario relative to the reference range."
)


def run(
    record: NormalizedCompanyRecord,
    *,
    metric: str,
    assumption_pct: float,
    periods_ahead: int = 3,
    guidance_low: Optional[float] = None,
    guidance_high: Optional[float] = None,
    sector_benchmark_pct: Optional[float] = None,
    with_narrative: bool = True,
) -> Dict[str, Any]:
    if metric not in FIELDS:
        raise ValueError(f"metric must be one of {', '.join(FIELDS)}")
    field = FIELDS[metric]

    refs = gather_reference_points(record, metric, guidance_low=guidance_low, guidance_high=guidance_high,
                                   sector_benchmark_pct=sector_benchmark_pct)
    classification = classify_assumption(assumption_pct, refs)
    drivers = growth_drivers(record, metric)

    # Macro growth is shown as context only; it is never blended into the comparison band.
    external_status = {
        "management_guidance": external.management_guidance(guidance_low, guidance_high).to_dict(),
        "macro_gdp_growth": external.macro_indicator(record.country).to_dict(),
        "analyst_estimates": external.analyst_estimates().to_dict(),
        "sector_benchmark": ({"status": "OK", "source_type": "user_input", "data": {"value": sector_benchmark_pct}}
                             if sector_benchmark_pct is not None else
                             {"status": "REQUIRES_EXTERNAL_DATA", "reason": "No sector benchmark was supplied."}),
    }

    projection = None
    series = extended._util.series(record, field)
    latest = extended._util.latest_point(series)
    if latest:
        projection = {
            "base_period": latest[0], "base_value": latest[1],
            "points": project_series(latest[1], latest[0], assumption_pct, periods_ahead),
        }

    result: Dict[str, Any] = {
        "metric": metric, "label": LABELS[metric], "assumption_pct": assumption_pct,
        "references": [r.model_dump() for r in refs], "classification": classification,
        "drivers": drivers, "projection": projection, "external": external_status,
        "currency": record.currency, "narrative": None,
    }
    if with_narrative and classification["verdict"] != "NO_REFERENCE_DATA":
        result["narrative"] = narrate(
            _ROLE,
            {"metric": LABELS[metric], "assumption_pct": assumption_pct, "verdict": classification["verdict"],
             "reference_range_pct": [classification["reference_low"], classification["reference_high"]],
             "deviation_pp": classification["deviation_pp"],
             "reference_points": [{"label": r.label, "value_pct": r.value_pct} for r in refs],
             "growth_drivers": drivers, "projection": projection},
            "Explain the reasoning behind this forecast using only the provided drivers, references and verdict.")
    return result
