"""Peer Matching Agent — V2

V2 REPLACEMENT: The V1 agent asked the LLM to hallucinate peer company
financials (estimated_revenue_usd, estimated_growth_rate, etc.).
ALL peer data was entirely fabricated.

V2 approach:
  1. LLM identifies peer company TICKERS (not financials)
  2. System FETCHES actual data via yfinance
  3. Deterministic comparison calculates relative metrics
  4. Result contains only REAL, fetched data

This module is now a thin wrapper — the actual logic is in agent_workflow.py's
peer_analysis_node. This module exists for backward compatibility with any
code that imports run_peer_matching directly.
"""
from __future__ import annotations

from typing import Any, Dict


def run_peer_matching(
    record: Any,
    saas_metrics: Dict[str, Any],
    base_url: str,
    model: str,
    api_key: str,
) -> Dict[str, Any]:
    """V2 peer matching — delegates to the agentic workflow.

    This function is maintained for backward compatibility.
    The actual peer matching with real data fetching is handled by
    the peer_analysis_node in agent_workflow.py.

    If called directly, returns a stub indicating that peer matching
    should be done through the full workflow pipeline.
    """
    return {
        "peers": [],
        "note": (
            "V2: Peer matching now uses real data fetching through the agent workflow. "
            "Run the full analysis pipeline via run_analysis() to get data-grounded peer comparisons."
        ),
    }
