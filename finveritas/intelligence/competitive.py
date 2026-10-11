"""Competitive intelligence: the target against its peers on ten metrics.

Peers are fetched (never guessed) and run through the SAME engines as the target, so a peer's
number is exactly as auditable as the target's own. Target value, peer median / mean and the gap are
all computed in Python; the LLM only narrates the resulting gaps. Ported from DeterminX
``src/competitive``.
"""
from __future__ import annotations

import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from finveritas.analysis.metrics import extended
from finveritas.analysis.metrics.profitability import compute_profitability_metrics
from finveritas.analysis.metrics.solvency import compute_solvency_metrics
from finveritas.ingestion.normalize import payload_to_normalized_record
from finveritas.intelligence.narrate import narrate
from finveritas.security import llm_guard
from finveritas.shared.schema import NormalizedCompanyRecord

TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")
MAX_PEERS = 5

# key, label, unit, ledger metric the value is read from
BENCHMARK = [
    ("revenue_cagr", "Revenue CAGR", "%", "revenue_cagr"),
    ("ebitda", "EBITDA", "absolute", None),
    ("ebitda_margin", "EBITDA margin", "%", "ebitda_margin"),
    ("pat_cagr", "Net profit CAGR", "%", "pat_cagr"),
    ("roe", "Return on equity", "%", "roe"),
    ("roce", "Return on capital employed", "%", "roce"),
    ("debt_to_equity", "Debt to equity", "ratio", "debt_to_equity"),
    ("net_margin", "Net profit margin", "%", "net_profit_margin"),
    ("gross_margin", "Gross margin", "%", "gross_margin"),
    ("asset_turnover", "Asset turnover", "ratio", "asset_turnover"),
]

_ROLE = (
    "You compare a company with its peers. Every gap and peer median is final. Describe where the company "
    "is stronger or weaker using only the provided rows; any suggested reason must be hedged as possible, "
    "never stated as fact. Write 5-8 concise, professional sentences."
)


def snapshot(record: NormalizedCompanyRecord) -> Dict[str, Optional[float]]:
    """The ten benchmark values for one company, from the same engines used everywhere else."""
    values: Dict[str, Optional[float]] = {}
    for e in [*compute_profitability_metrics(record), *compute_solvency_metrics(record)]:
        values.setdefault(e.metric, e.value if isinstance(e.value, (int, float)) else None)
    ledger, _ = extended.build_extended_ledger(record)
    for e in ledger.entries:
        if isinstance(e.value, (int, float)):
            values.setdefault(e.metric, e.value)

    u = extended._util
    ebitda = u.latest_point(u.series(record, "ebitda"))
    if ebitda is None:
        oi, dep = u.series(record, "operating_income"), u.series(record, "depreciation")
        both = {p: oi[p] + dep[p] for p in set(oi) & set(dep)}
        ebitda = u.latest_point(both)
    out = {key: values.get(src) if src else None for key, _, _, src in BENCHMARK}
    out["ebitda"] = ebitda[1] if ebitda else None
    return out


def _fetch_peer(ticker: str) -> Dict[str, Any]:
    from finveritas.ingestion.ticker import fetch_by_ticker
    try:
        payload = fetch_by_ticker(ticker)
        rec = payload_to_normalized_record(payload, "ticker")
        return {"ticker": ticker, "name": rec.entity_id, "currency": rec.currency, "metrics": snapshot(rec)}
    except Exception as exc:
        return {"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"}


def benchmark(target: NormalizedCompanyRecord, peers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Target vs peer median / mean / gap for each metric. Pure Python."""
    mine = snapshot(target)
    rows = []
    for key, label, unit, _ in BENCHMARK:
        usable = [p for p in peers if p.get("metrics", {}).get(key) is not None]
        if unit == "absolute":  # an amount is only comparable between companies reporting in one currency
            usable = [p for p in usable if p.get("currency") == target.currency]
        vals = [p["metrics"][key] for p in usable]
        t = mine.get(key)
        med = statistics.median(vals) if vals else None
        rows.append({
            "key": key, "label": label, "unit": unit, "target": t,
            "peer_values": [{"ticker": p["ticker"], "value": p["metrics"][key]} for p in usable],
            "peer_median": med, "peer_mean": statistics.fmean(vals) if vals else None,
            "gap": (t - med) if t is not None and med is not None else None, "peer_count": len(vals),
        })
    return rows


def run(target: NormalizedCompanyRecord, tickers: List[str], *, with_narrative: bool = True) -> Dict[str, Any]:
    clean: List[str] = []
    for t in tickers:
        t = str(t).strip().upper()
        if t and TICKER_RE.match(t) and t not in clean and t != (target.ticker_symbol or "").upper():
            clean.append(t)
    clean = clean[:MAX_PEERS]
    if not clean:
        return {"status": "UNAVAILABLE", "reason": "No valid peer tickers to compare against.", "rows": [], "peers": []}

    with ThreadPoolExecutor(max_workers=len(clean)) as pool:
        fetched = list(pool.map(_fetch_peer, clean))
    ok = [p for p in fetched if "metrics" in p]
    failed = [{"ticker": p["ticker"], "reason": p["error"]} for p in fetched if "error" in p]
    if not ok:
        return {"status": "UNAVAILABLE", "reason": "None of the peers' data could be fetched.", "rows": [],
                "peers": [], "failed": failed}

    rows = benchmark(target, ok)
    result: Dict[str, Any] = {
        "status": "OK", "currency": target.currency, "rows": rows, "failed": failed, "narrative": None,
        "peers": [{"ticker": p["ticker"], "name": p["name"], "currency": p["currency"]} for p in ok],
    }
    if with_narrative:
        result["narrative"] = narrate(
            _ROLE,
            {"company": llm_guard.safe_entity_name(target.entity_id), "peers": [p["name"] for p in ok],
             "rows": [{k: r[k] for k in ("label", "unit", "target", "peer_median", "gap", "peer_count")} for r in rows]},
            "Compare the company with its peers using only these rows.")
    return result
