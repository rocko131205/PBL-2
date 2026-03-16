"""Cross Reference Agent

Takes outputs from multiple deterministic agents and produces a consolidated
explainable summary via an LLM.

Constraints:
- Must not calculate new numbers.
- Must use only provided metrics and qualitative flags.
- No credit decisions.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


def run(
    *,
    entity: str,
    revenue: dict[str, Any],
    liquidity: dict[str, Any],
    balance_sheet: dict[str, Any],
    base_url: str,
    model: str,
    api_key: str = "local",
) -> dict[str, Any]:
    """Generate a cross-referenced explanation using only agent metrics."""

    # Only pass metrics to the LLM, not raw time series.
    payload = {
        "entity": entity,
        "inputs": {
            "revenue_metrics": revenue.get("metrics"),
            "liquidity_metrics": liquidity.get("metrics"),
            "balance_sheet_metrics": balance_sheet.get("metrics"),
        },
        "requirements": {
            "no_new_numbers": True,
            "no_credit_decisions": True,
            "professional_tone": True,
            "temperature": 0,
        },
    }

    system = (
        "You are a financial analyst producing an explainable, cross-referenced summary. "
        "Use only the provided metrics. "
        "Do not compute, estimate, or infer any new numbers. "
        "Do not introduce new financial line items. "
        "Do not provide credit, lending, or investment recommendations. "
        "Write in a concise professional tone (6-10 sentences)."
    )

    human = {
        "task": "Cross-reference the metrics to describe overall financial trends and highlight any consistency or tension between signals.",
        **payload,
        "output": {
            "format": "plain_text",
            "must_include": [
                "a short revenue summary",
                "a short liquidity summary",
                "a short balance sheet/leverage summary",
                "one integrated concluding sentence",
            ],
        },
    }

    llm = ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=0,
    )

    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=json.dumps(human, indent=2))])
    text = getattr(resp, "content", None)
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("LLM returned empty cross-reference analysis")

    return {
        "entity": entity,
        "metrics": {
            "revenue": revenue.get("metrics"),
            "liquidity": liquidity.get("metrics"),
            "balance_sheet": balance_sheet.get("metrics"),
        },
        "analysis": text.strip(),
    }
