from __future__ import annotations
from typing import Any, Dict, TypedDict, Optional
from pydantic import BaseModel
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from .schema import NormalizedCompanyRecord, DSCRInputs
from .dscr_engine import compute_dscr

# Define the State for LangGraph
class WorkflowState(TypedDict):
    company_record: Optional[NormalizedCompanyRecord]
    missing_fields: list[str]
    dscr_inputs: Optional[DSCRInputs]
    requires_human_input: bool
    human_input_prompt: str
    dscr_ratio: Optional[float]
    saas_metrics: Optional[Dict[str, Any]]
    peers: Optional[Dict[str, Any]]
    credit_risk_report: Optional[Dict[str, Any]]
    llm_config: Optional[Dict[str, str]]

# Node 1: Check Data Sufficiency
def check_data_sufficiency(state: WorkflowState) -> WorkflowState:
    """
    Checks if we have all the required data to proceed with the DSCR 
    calculation and credit analysis.
    """
    record = state.get("company_record")
    dscr_inputs = state.get("dscr_inputs")
    
    missing = []
    
    if not record:
        missing.append("Company Financials")
        
    if not dscr_inputs:
        missing.extend([
            "existing_loan_principal_repayment",
            "existing_loan_interest",
            "proposed_loan_principal_repayment",
            "proposed_loan_interest"
        ])
    else:
        # Check specific fields if partially provided (if we allowed dicts)
        pass
    
    requires_human_input = len(missing) > 0
    prompt = ""
    if requires_human_input:
        prompt = f"The following information is missing for DSCR calculation: {', '.join(missing)}. Please provide it."
        
    return {
        "company_record": record,
        "missing_fields": missing,
        "dscr_inputs": dscr_inputs,
        "requires_human_input": requires_human_input,
        "human_input_prompt": prompt,
        "dscr_ratio": state.get("dscr_ratio"),
        "credit_risk_report": state.get("credit_risk_report")
    }

# Node 2: Calculate DSCR
def compute_dscr_node(state: WorkflowState) -> WorkflowState:
    """
    Deterministically computes the DSCR once data is sufficient.
    """
    if state["requires_human_input"]:
        return state # Skip if we don't have data
        
    record = state["company_record"]
    dscr_inputs = state["dscr_inputs"]
    
    try:
        dscr_results = compute_dscr(record, dscr_inputs)
        dscr_ratio = dscr_results["dscr_ratio"]
    except ValueError:
        dscr_ratio = None
    
    return {
        **state,
        "dscr_ratio": dscr_ratio
    }

# Router Function
def route_after_sufficiency(state: WorkflowState):
    if state["requires_human_input"]:
        return "human_input_required"
    return "compute_dscr"

from .saas_engine import compute_saas_metrics
from .peer_matching_agent import run_peer_matching
from .credit_risk_agent import run_credit_risk_assessment

# Node 3: Synthesize and Peer Match
def synthesize_and_peer_match(state: WorkflowState) -> WorkflowState:
    record = state["company_record"]
    saas_metrics = compute_saas_metrics(record)
    
    llm_config = state.get("llm_config", {})
    base_url = llm_config.get("base_url", "")
    model = llm_config.get("model", "")
    api_key = llm_config.get("api_key", "")
    
    peers_res = run_peer_matching(record, saas_metrics, base_url, model, api_key)
    peers = peers_res.get("peers", {})
    
    return {
        **state,
        "saas_metrics": saas_metrics,
        "peers": peers
    }

# Node 4: Credit Risk Agent
def credit_risk_assessment(state: WorkflowState) -> WorkflowState:
    record = state["company_record"]
    dscr_ratio = state["dscr_ratio"] or 0.0
    saas_metrics = state["saas_metrics"] or {}
    peers = state["peers"] or {}
    
    llm_config = state.get("llm_config", {})
    base_url = llm_config.get("base_url", "")
    model = llm_config.get("model", "")
    api_key = llm_config.get("api_key", "")
    
    report_res = run_credit_risk_assessment(record, dscr_ratio, saas_metrics, peers, base_url, model, api_key)
    
    return {
        **state,
        "credit_risk_report": report_res.get("report")
    }

# Build the Graph
workflow = StateGraph(WorkflowState)

workflow.add_node("check_data_sufficiency", check_data_sufficiency)
workflow.add_node("compute_dscr", compute_dscr_node)
workflow.add_node("peer_matching", synthesize_and_peer_match)
workflow.add_node("credit_risk", credit_risk_assessment)

workflow.set_entry_point("check_data_sufficiency")
workflow.add_conditional_edges(
    "check_data_sufficiency",
    route_after_sufficiency,
    {
        "human_input_required": END,
        "compute_dscr": "compute_dscr"
    }
)
workflow.add_edge("compute_dscr", "peer_matching")
workflow.add_edge("peer_matching", "credit_risk")
workflow.add_edge("credit_risk", END)

finveritas_v2_app = workflow.compile()
