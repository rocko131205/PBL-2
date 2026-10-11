"""External data layer.

Everything the intelligence agents need that FinVeritas does not compute itself sits
behind a provider that returns a ``ProviderResult``, never a raw untyped payload.
Ported from DeterminX ``src/external``.

Rules every provider follows:
* If it cannot reliably answer it returns UNAVAILABLE / ERROR / NOT_CONFIGURED, never a
  made-up value. Callers never need their own try/except.
* Every result carries its source and retrieval time so the UI can tell a financial fact
  from an external fact from an AI interpretation.
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import requests

OK, UNAVAILABLE, ERROR, NOT_CONFIGURED = "OK", "UNAVAILABLE", "ERROR", "NOT_CONFIGURED"
_TIMEOUT = 8.0


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    source_type: str
    status: str                       # OK | UNAVAILABLE | ERROR | NOT_CONFIGURED
    data: Any = None
    reason: Optional[str] = None
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_reference: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == OK

    def to_dict(self) -> dict:
        return asdict(self)


def _guard(provider: str, source_type: str, fn: Callable[[], ProviderResult]) -> ProviderResult:
    """Run a provider call; any exception becomes an ERROR result instead of propagating."""
    try:
        return fn()
    except Exception as exc:  # network / library errors of any shape
        return ProviderResult(provider, source_type, ERROR, reason=f"{type(exc).__name__}: {exc}")


# ── Macro indicators: World Bank Open Data (free, keyless) ───────────────────

INDICATOR_GDP_GROWTH = "NY.GDP.MKTP.KD.ZG"
_WB_URL = "https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"


def macro_indicator(country_code: Optional[str], indicator: str = INDICATOR_GDP_GROWTH) -> ProviderResult:
    name, kind = "world_bank", "macro_indicator"

    def run() -> ProviderResult:
        code = re.sub(r"[^A-Za-z]", "", country_code or "").upper()
        if len(code) not in (2, 3):
            return ProviderResult(name, kind, UNAVAILABLE, reason="No valid country code for this company.")
        url = _WB_URL.format(country=code, indicator=indicator)
        resp = requests.get(url, params={"format": "json", "per_page": 6, "mrnev": 3}, timeout=_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, list) or len(body) < 2 or not body[1]:
            return ProviderResult(name, kind, UNAVAILABLE, reason=f"No data returned for '{code}'.")
        series = [{"year": r.get("date"), "value": r.get("value")} for r in body[1] if r.get("value") is not None]
        if not series:
            return ProviderResult(name, kind, UNAVAILABLE, reason=f"World Bank has no observations for '{code}'.")
        return ProviderResult(name, kind, OK, raw_reference=url, data={
            "country": code, "indicator": indicator, "latest_year": series[0]["year"],
            "latest_value_pct": series[0]["value"], "series": series})

    return _guard(name, kind, run)


# ── Management guidance: user-entered only ───────────────────────────────────

def management_guidance(low: Optional[float], high: Optional[float]) -> ProviderResult:
    name, kind = "management_guidance", "user_input"
    if low is None and high is None:
        return ProviderResult(name, kind, UNAVAILABLE, reason="No management guidance was entered.")
    return ProviderResult(name, kind, OK, data={"low": low, "high": high})


# ── Not configured in this deployment (no licensed / public keyless source) ──

def analyst_estimates() -> ProviderResult:
    return ProviderResult("analyst_estimates", "analyst_consensus", NOT_CONFIGURED,
                          reason="No licensed analyst-consensus feed (I/B/E/S, Visible Alpha, Bloomberg) is configured.")


def governance_registry(subject: str) -> ProviderResult:
    return ProviderResult(
        "governance_registry", "statutory_registry", NOT_CONFIGURED,
        reason=f"No MCA / SEBI / IBBI data-partner feed is configured, so statutory records for "
               f"'{subject or 'this director'}' could not be checked.")


# ── News: NewsAPI ────────────────────────────────────────────────────────────

_LEGAL_SUFFIX = re.compile(
    r"\s+(?:limited|ltd\.?|inc\.?|incorporated|corp\.?|corporation|plc|llc|pvt\.?\s*ltd\.?|"
    r"private\s+limited|co\.?|company)\s*$", re.IGNORECASE)


def company_search_name(entity: str) -> str:
    """Drop a trailing legal suffix: news rarely prints 'Tata Consultancy Services Limited' verbatim."""
    return _LEGAL_SUFFIX.sub("", (entity or "").strip()).strip() or (entity or "")


def news_api_key() -> str:
    return (os.getenv("NEWSAPI_KEY") or os.getenv("NEWS_API_KEY") or "").strip()


def news(query: str, max_articles: int = 10) -> ProviderResult:
    name, kind = "newsapi", "news"
    key = news_api_key()
    if not key:
        return ProviderResult(name, kind, NOT_CONFIGURED, reason="No NewsAPI key is configured (set NEWSAPI_KEY).")

    def run() -> ProviderResult:
        url = "https://newsapi.org/v2/everything"
        resp = requests.get(url, timeout=_TIMEOUT, headers={"X-Api-Key": key},
                            params={"q": query, "language": "en", "sortBy": "publishedAt",
                                    "pageSize": max(1, min(max_articles, 20))})
        resp.raise_for_status()
        body = resp.json()
        articles = [{"title": a.get("title"), "description": a.get("description"),
                     "source": (a.get("source") or {}).get("name"), "publishedAt": a.get("publishedAt"),
                     "url": a.get("url")} for a in (body.get("articles") or [])]
        if not articles:
            return ProviderResult(name, kind, UNAVAILABLE, reason=f"No recent articles found for '{query}'.")
        return ProviderResult(name, kind, OK, data={"articles": articles, "query": query}, raw_reference=url)

    return _guard(name, kind, run)
