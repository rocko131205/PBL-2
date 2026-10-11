"""Geography-wise revenue analysis.

Regional revenue, share of total, YoY growth and volatility are computed entirely in Python from
figures the user enters (or confirms after a best-effort extraction from pasted segment-note text:
Bloomberg statement exports don't carry a geographic segment note). For a region with a notable
swing, recent headlines are shown to the LLM, which must keep the computed FACT separate from any
POSSIBLE EXPLANATION and say so when no headline mentions the company. Ported from DeterminX
``src/geography``.
"""
from __future__ import annotations

import re
import statistics
from typing import Any, Dict, Optional

from finveritas.analysis.metrics.extended import _util as u
from finveritas.intelligence import external
from finveritas.intelligence.narrate import narrate
from finveritas.security import llm_guard
from finveritas.shared.schema import NormalizedCompanyRecord

NOTABLE_SWING_PCT = 15.0
MAX_REGIONS = 20
MAX_PERIODS = 10

_ROLE = (
    "You explain regional revenue performance. Structure the answer as a 'FACT:' section restating the computed "
    "numbers, then a 'POSSIBLE EXPLANATION:' section only for notable-swing regions. In the second section, "
    "frame any cause as possible, never established, use only the provided headlines, and say explicitly when no "
    "headline mentions the company or the region. Keep it concise."
)

_REGIONS = [
    "North America", "United States", "Europe", "Asia Pacific", "APAC", "India", "China", "Japan",
    "Latin America", "Middle East", "Africa", "Rest of World", "Domestic", "International",
]
_NUMBER = r"[\$₹€£]?\s?([\d,]+(?:\.\d+)?)"
_LINE_PATTERNS = [re.compile(rf"^\s*{re.escape(r)}\D{{0,20}}{_NUMBER}", re.IGNORECASE) for r in _REGIONS]


def extract_regional_revenue(text: str, period: str) -> Dict[str, Dict[str, float]]:
    """Best-effort {region: {period: value}} from pasted segment-note text. Never raises; empty if nothing fits.

    It is a starting point the user must confirm, not an authoritative source.
    """
    found: Dict[str, Dict[str, float]] = {}
    for region, pattern in zip(_REGIONS, _LINE_PATTERNS):
        for line in (text or "").splitlines():
            m = pattern.match(line)
            if m:
                try:
                    found[region] = {period: float(m.group(1).replace(",", ""))}
                except ValueError:
                    continue
                break
    return found


def compute_regional_metrics(regional: Dict[str, Dict[str, float]], total: Dict[str, float]) -> Dict[str, Any]:
    """Pure Python: revenue, share of total, YoY growth and volatility per region."""
    out: Dict[str, Any] = {}
    for region, series in regional.items():
        periods = sorted(series, key=u.period_key)
        if not periods:
            continue
        values = [series[p] for p in periods]
        shares = [round(v / total[p] * 100, 2) if total.get(p) else None for p, v in zip(periods, values)]
        growth = [None] + [round((values[i] - values[i - 1]) / abs(values[i - 1]) * 100, 2) if values[i - 1] else None
                           for i in range(1, len(values))]
        clean = [g for g in growth if g is not None]
        latest = growth[-1]
        out[region] = {
            "periods": periods, "revenue": values, "revenue_share_pct": shares, "yoy_growth_pct": growth,
            "volatility": round(statistics.pstdev(clean), 3) if len(clean) >= 2 else None,
            "latest_yoy_growth_pct": latest,
            "notable_swing": isinstance(latest, (int, float)) and abs(latest) >= NOTABLE_SWING_PCT,
        }
    return out


def run(record: NormalizedCompanyRecord, regional: Dict[str, Dict[str, float]], *,
        with_narrative: bool = True) -> Dict[str, Any]:
    if not regional:
        return {"status": "UNAVAILABLE",
                "reason": "No regional revenue was entered. The regional split comes from the segment-reporting "
                          "note of an annual report, which a statement export doesn't contain, so enter it to enable this."}
    total = u.series(record, "revenue")
    metrics = compute_regional_metrics(regional, total)
    notable = [r for r, m in metrics.items() if m["notable_swing"]]

    news_by_region: Dict[str, Any] = {}
    for region in notable:
        res = external.news(f"{external.company_search_name(record.entity_id)} {region}", max_articles=5)
        news_by_region[region] = res.to_dict()

    result: Dict[str, Any] = {
        "status": "OK", "currency": record.currency, "region_metrics": metrics, "notable_regions": notable,
        "news_status": {r: d["status"] for r, d in news_by_region.items()},
        "headlines": {r: (d["data"]["articles"][:5] if d["status"] == "OK" else []) for r, d in news_by_region.items()},
        "narrative": None,
    }
    if with_narrative:
        headline_text = "\n".join(
            f"[{r}] {a.get('title')} ({a.get('source')}, {str(a.get('publishedAt'))[:10]})"
            for r, arts in result["headlines"].items() for a in arts)
        result["narrative"] = narrate(
            _ROLE,
            {"company": llm_guard.safe_entity_name(record.entity_id), "currency": record.currency, "region_metrics": metrics,
             "notable_regions": notable,
             "news_status": {r: d["status"] for r, d in news_by_region.items()}},
            "Narrate the regional revenue picture, keeping the computed FACT separate from any POSSIBLE EXPLANATION.",
            untrusted={"news_headlines": headline_text} if headline_text else None)
    return result
