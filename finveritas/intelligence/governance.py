"""Governance: executive background screen.

    director/DIN extraction -> statutory registry (not configured) -> deterministic adverse-mention
    keyword screen over recent headlines -> LLM narrates

A keyword match in a headline is a COUNT ("N articles mention this term near the name"), never an
accusation. It is always worded "requires manual verification", the statutory lookup is reported as
not-configured instead of implying a clean record, and governance is reported SEPARATELY from financial
health, never blended into a single score. Ported from DeterminX ``src/governance``.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from finveritas.intelligence import external
from finveritas.intelligence.narrate import narrate
from finveritas.security import llm_guard
from finveritas.shared.schema import NormalizedCompanyRecord

MAX_DIRECTORS = 12

_ROLE = (
    "You summarise governance findings. Use ONLY the provided findings and imply nothing beyond them. A keyword "
    "match in a headline is NOT proof of wrongdoing: always call matches 'requires manual verification'. If the "
    "statutory registry is NOT_CONFIGURED say plainly that statutory records could not be checked, rather than "
    "implying a clean record. Keep this entirely separate from any financial-health view. Write 4-8 concise, "
    "professional sentences."
)

RED_FLAG_KEYWORDS = frozenset({
    "fraud", "fraudulent", "investigation", "investigated", "disqualified", "disqualification", "insolvency", "ibbi",
    "sebi action", "sebi order", "banned", "debarred", "resign", "resigned", "resignation", "lawsuit",
    "charge-sheeted", "chargesheet", "arrested", "conviction", "convicted", "penalty", "penalised", "penalized",
    "default", "willful defaulter", "shell company", "money laundering", "embezzlement",
})

_DIN = re.compile(r"\bDIN\s*[:\-]?\s*(\d{8})\b", re.IGNORECASE)
# "Jane Doe (DIN: 01234567)" / "Jane Doe, DIN 01234567" / "Jane Doe - DIN: 01234567"
_NAME_DIN = re.compile(r"([A-Z][A-Za-z\.\s]{2,40}?)\s*[\(,\-–]\s*DIN\s*[:\-]?\s*(\d{8})")


def extract_directors(text: str) -> List[Dict[str, str]]:
    """Best-effort [{name, din}] from filing text. Empty when nothing fits; the user confirms or edits the result."""
    found: Dict[str, str] = {}
    # Line by line: the name group's \s would otherwise let a trailing title bleed into the next director's name.
    for line in (text or "").splitlines():
        for m in _NAME_DIN.finditer(line):
            name = re.sub(r"\s+", " ", m.group(1)).strip(" .,-")
            if name:
                found[m.group(2)] = name
    for m in _DIN.finditer(text or ""):
        found.setdefault(m.group(1), "")
    return [{"name": name, "din": din} for din, name in found.items()]


def screen_articles(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    matches = []
    for art in articles:
        text = f"{art.get('title') or ''} {art.get('description') or ''}".lower()
        hits = sorted(k for k in RED_FLAG_KEYWORDS if k in text)
        if hits:
            matches.append({"title": art.get("title"), "url": art.get("url"), "publishedAt": art.get("publishedAt"),
                            "source": art.get("source"), "matched_keywords": hits})
    return {"articles_scanned": len(articles), "matches": matches}


def run(record: NormalizedCompanyRecord, directors: List[Dict[str, str]], *, with_narrative: bool = True) -> Dict[str, Any]:
    directors = [d for d in directors if (d.get("name") or d.get("din"))][:MAX_DIRECTORS]
    if not directors:
        return {"status": "UNAVAILABLE", "reason": "No directors were supplied. Extract them from a filing or enter them manually."}

    company = external.company_search_name(record.entity_id)
    findings: List[Dict[str, Any]] = []
    for d in directors:
        name, din = (d.get("name") or "").strip(), (d.get("din") or "").strip() or None
        statutory = external.governance_registry(din or name)
        screen = {"articles_scanned": 0, "matches": []}
        news_status = "UNAVAILABLE"
        if name:
            res = external.news(f'"{name}" {company}', max_articles=10)
            news_status = res.status
            if res.ok:
                screen = screen_articles(res.data["articles"])
        status = "WARN" if screen["matches"] else "PASS" if screen["articles_scanned"] else "UNAVAILABLE"
        findings.append({"name": name or "(name not provided)", "din": din or "(DIN not provided)",
                         "statutory_lookup": statutory.to_dict(), "news_status": news_status,
                         "adverse_mention_screen": screen, "status": status})

    overall = ("WARN" if any(f["status"] == "WARN" for f in findings)
               else "UNAVAILABLE" if all(f["status"] == "UNAVAILABLE" for f in findings) else "PASS")
    result: Dict[str, Any] = {"status": "OK", "overall": overall, "findings": findings, "narrative": None}
    if with_narrative:
        facts = [{"name": f["name"], "din": f["din"], "status": f["status"],
                  "statutory_registry": f["statutory_lookup"]["status"], "news_status": f["news_status"],
                  "articles_scanned": f["adverse_mention_screen"]["articles_scanned"],
                  "matches": [{"keywords": m["matched_keywords"]} for m in f["adverse_mention_screen"]["matches"]]}
                 for f in findings]
        # Headlines are third-party text: they go through the spotlighted untrusted channel, never the facts.
        headlines = "\n".join(f"[{f['name']}] {m['title']}" for f in findings
                              for m in f["adverse_mention_screen"]["matches"])
        result["narrative"] = narrate(
            _ROLE, {"company": llm_guard.safe_entity_name(record.entity_id), "findings": facts},
            "Summarise the governance findings for these directors using only the provided data.",
            untrusted={"matched_headlines": headlines} if headlines else None)
    return result
