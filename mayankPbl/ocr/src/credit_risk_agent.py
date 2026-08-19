"""Credit Risk Agent — V2

V2 REFACTOR: The V1 agent sent DSCR + Rule-of-40 to the LLM and asked it
to generate a JSON risk report. The LLM was the sole source of the risk rating,
analysis, and recommendation — entirely ungrounded.

V2 approach:
  - Receives the FULL fact ledger (all deterministic metrics)
  - Receives peer comparison data (actual, not hallucinated)
  - Receives qualitative evidence (structured extraction)
  - Receives data credibility report
  - Risk classification is DETERMINISTIC (from risk_indicator_engine)
  - LLM synthesizes a narrative but CANNOT override deterministic classifications
  - Output as CreditAssessmentReport Pydantic model

This module is now a thin wrapper — the actual logic is in agent_workflow.py's
credit_assessment_node. This module exists for backward compatibility.
"""
from __future__ import annotations

from typing import Any, Dict


def run_credit_risk_assessment(
    record: Any,
    dscr_ratio: float,
    saas_metrics: Dict[str, Any],
    peers: Dict[str, Any],
    base_url: str,
    model: str,
    api_key: str,
) -> Dict[str, Any]:
    """V2 credit risk assessment — delegates to the agentic workflow.

    This function is maintained for backward compatibility.
    The actual credit assessment is handled by the credit_assessment_node
    in agent_workflow.py, which receives the full fact ledger and produces
    a CreditAssessmentReport.

    If called directly, returns a stub indicating that the assessment
    should be done through the full workflow pipeline.
    """
    return {
        "report": {
            "risk_rating": "Unknown",
            "analysis": (
                "V2: Credit risk assessment now uses the full fact ledger and "
                "deterministic risk classification. Run the full analysis pipeline "
                "via run_analysis() to get a comprehensive, grounded credit report."
            ),
            "recommendation": (
                "Please run the full V2 analysis pipeline for a complete assessment."
            ),
        }
    }
