"""Reporting-scale detection & normalization (V3).

Financial statements are usually reported in a scaled unit — "₹ in millions",
"figures in lakhs", "Rs. in crore", "in thousands". If we store the face numbers
without applying that scale, magnitudes are wildly wrong (e.g. Infosys total
assets show as ₹1.49M instead of ₹1,48,903 crore).

This module detects the scale from statement text and rescales a payload to
ABSOLUTE currency units so every downstream number (and its display) is correct.

Note: yfinance already returns absolute values, so its payloads should NOT be
rescaled — only apply detection to PDF/CSV text sources, or let the user confirm.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple

# label -> (multiplier, regex). Ordered by specificity/size.
_SCALES: list[tuple[str, float, str]] = [
    ("crore",    1e7, r"\b(?:in\s+)?(?:rs\.?|₹|inr)?\s*crores?\b|\bin\s+cr\b"),
    ("lakh",     1e5, r"\b(?:in\s+)?(?:rs\.?|₹|inr)?\s*(?:lakhs?|lacs?)\b"),
    ("billion",  1e9, r"\b(?:in\s+)?billions?\b|\bin\s+bn\b"),
    ("million",  1e6, r"\b(?:in\s+)?millions?\b|\bin\s+mn\b|figures?\s+in\s+millions?"),
    ("thousand", 1e3, r"\b(?:in\s+)?thousands?\b|\bin\s+000s?\b"),
]

SCALE_MULTIPLIERS: Dict[str, float] = {
    "absolute": 1.0, "thousand": 1e3, "lakh": 1e5, "million": 1e6,
    "crore": 1e7, "billion": 1e9,
}


def detect_scale(text: str) -> Tuple[float, str]:
    """Detect the reporting scale from statement text.

    Returns (multiplier, label). Defaults to (1.0, 'absolute') if nothing found.
    """
    if not text:
        return 1.0, "absolute"
    low = text.lower()
    for label, mult, pattern in _SCALES:
        if re.search(pattern, low):
            return mult, label
    return 1.0, "absolute"


def rescale_payload(payload: Dict[str, Any], multiplier: float) -> Dict[str, Any]:
    """Return a copy of the payload with every time-series value multiplied.

    Records the applied scale under entity['reported_scale_multiplier'].
    Multiplier of 1.0 returns the payload unchanged (aside from the annotation).
    """
    import copy
    out = copy.deepcopy(payload)
    entity = out.setdefault("entity", {})
    entity["reported_scale_multiplier"] = multiplier
    if multiplier == 1.0:
        return out
    ts = out.get("time_series") or {}
    for field, series in ts.items():
        if not isinstance(series, list):
            continue
        for item in series:
            if isinstance(item, dict) and item.get("value") is not None:
                try:
                    item["value"] = float(item["value"]) * multiplier
                except (ValueError, TypeError):
                    pass
    return out
