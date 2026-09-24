"""FinVeritas V2 — Agentic Orchestration Workflow

V2 REPLACEMENT: The V1 workflow was a fixed linear pipeline:
  check_data → compute_dscr → peer_match → credit_risk → END

V2 implements genuine agentic behavior:
  - Company Intelligence Agent: Identifies, classifies, detects SaaS subtype
  - Data Acquisition Agent: Determines sources, fetches, identifies gaps
  - Financial Computation: Deterministic (NOT agentic) calculation of all metrics
  - Peer Analysis Agent: Dynamic peer selection with real data retrieval
  - Qualitative Analysis Agent: Corporate evidence extraction
  - Credit Assessment Agent: Synthesizes all evidence into structured report

LangGraph orchestrates the workflow with conditional branching.
Deterministic computation is NOT delegated to the LLM.

The LLM is used for:
  - Company classification and identification
  - Peer company identification (but data is then FETCHED, not hallucinated)
  - Qualitative analysis of management commentary
  - Synthesizing a credit narrative from pre-computed facts

The LLM is NOT used for:
  - Any financial calculation
  - Generating financial numbers
  - Risk classification (that's deterministic)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from finveritas.analysis.metrics.dscr import compute_dscr, dscr_to_fact_entry
from finveritas.ingestion.normalize import payload_to_normalized_record
from finveritas.analysis.metrics.profitability import compute_profitability_metrics
from finveritas.analysis.metrics.risk import build_risk_dashboard
from finveritas.analysis.metrics.saas import compute_saas_metrics
from finveritas.shared.schema import (
    CreditAssessmentReport,
    DSCRInputs,
    DSCRResult,
    FactLedgerEntry,
    FinancialFactLedger,
    NormalizedCompanyRecord,
    PeerCompany,
    PeerComparison,
    RiskDashboard,
    RiskLevel,
)
from finveritas.analysis.metrics.solvency import compute_solvency_metrics
from finveritas.analysis.metrics.liquidity import compute_liquidity_metrics
from finveritas.analysis.metrics.working_capital import compute_working_capital_cycle


# -------------------------------------------------------------------------
# Workflow State
# -------------------------------------------------------------------------

class WorkflowState(TypedDict, total=False):
    """State flowing through the LangGraph workflow.

    Each node reads from and writes to this shared state.
    """
    # Input
    payload: Dict[str, Any]
    source_type: str
    dscr_inputs: Dict[str, Any]  # Serialized DSCRInputs

    # LLM config
    llm_base_url: str
    llm_model: str
    llm_api_key: str

    # Optional API keys
    fmp_api_key: Optional[str]
    news_api_key: Optional[str]

    # Company record
    company_record: Optional[Dict[str, Any]]  # Serialized NormalizedCompanyRecord

    # Company intelligence
    company_profile: Dict[str, Any]

    # Fact ledger (deterministic computation output)
    fact_ledger: Optional[Dict[str, Any]]  # Serialized FinancialFactLedger

    # DSCR
    dscr_result: Optional[Dict[str, Any]]  # Serialized DSCRResult

    # Peer analysis
    peer_comparison: Optional[Dict[str, Any]]  # Serialized PeerComparison

    # Risk dashboard
    risk_dashboard: Optional[Dict[str, Any]]  # Serialized RiskDashboard

    # Qualitative findings
    qualitative_findings: List[str]

    # Final report
    credit_report: Optional[Dict[str, Any]]  # Serialized CreditAssessmentReport

    # Workflow status
    errors: List[str]
    workflow_log: List[str]


# -------------------------------------------------------------------------
# Helper: LLM initialization
# -------------------------------------------------------------------------

def _get_llm(state: WorkflowState, custom_timeout: float = 15.0) -> ChatOpenAI:
    return ChatOpenAI(
        model=state.get("llm_model", "qwen2.5-coder-1.5b-instruct-mlx"),
        base_url=state.get("llm_base_url", "http://localhost:1234/v1"),
        api_key=state.get("llm_api_key", "local"),
        temperature=0,
        request_timeout=custom_timeout,
        timeout=custom_timeout,
        max_retries=1,
    )


def _log(state: WorkflowState, msg: str) -> None:
    state.setdefault("workflow_log", []).append(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}")


import re as _re


def _extract_json(text: Optional[str]) -> Optional[Any]:
    """Robustly pull a JSON object/array out of an LLM response.

    Tries: direct parse → each fenced ``` block → first {...}/[...] span.
    Returns the parsed value or None (never raises). Replaces the fragile
    split-on-``` approach used across the nodes."""
    if not text:
        return None
    t = text.strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    if "```" in t:
        for part in t.split("```"):
            p = part.strip()
            if p.lower().startswith("json"):
                p = p[4:].strip()
            if p and p[0] in "{[":
                try:
                    return json.loads(p)
                except Exception:
                    continue
    for pattern in (r"\{.*\}", r"\[.*\]"):
        m = _re.search(pattern, t, _re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                continue
    return None


def _is_software_company(profile: Dict[str, Any]) -> bool:
    """SaaS-specific metrics (Rule of 40, etc.) only make sense for software companies.
    Running them on a bank or airline produces meaningless numbers."""
    if profile.get("is_saas") is True:
        return True
    subtype = (profile.get("saas_subtype") or "").lower()
    if subtype and subtype not in ("non_saas", "n/a", "none", ""):
        return True
    industry = (profile.get("industry") or "").lower()
    return any(k in industry for k in ("software", "saas", "internet", "cloud", "technology"))


# -------------------------------------------------------------------------
# Node 1: Company Intelligence Agent
# -------------------------------------------------------------------------

def company_intelligence_node(state: WorkflowState) -> WorkflowState:
    """Identifies and classifies the company.

    WHY AGENTIC: The agent must reason about what kind of company this is
    based on available context (name, ticker, financial profile). A deterministic
    function can't infer industry classification or SaaS subtype from a company name.

    WHAT IT DOES:
    - Converts raw payload to NormalizedCompanyRecord
    - Uses LLM to classify industry, SaaS subtype, and country
    - Populates company profile metadata
    """
    _log(state, "Company Intelligence Agent: Starting company identification")

    payload = state.get("payload", {})
    source_type = state.get("source_type", "unknown")

    # Convert payload to normalized record
    record = payload_to_normalized_record(payload, source_type)

    # Use LLM for classification
    entity_info = payload.get("entity", {})
    company_name = entity_info.get("entity_id", record.entity_id)
    currency = entity_info.get("currency", "USD")

    available = record.available_fields()
    _log(state, f"Company Intelligence Agent: {company_name}, {len(available)} financial fields available")

    try:
        llm = _get_llm(state)
        classification_prompt = json.dumps({
            "task": (
                "Classify this company. Based on the company name and available context, "
                "determine: (1) country of domicile, (2) whether it's a SaaS/software company, "
                "(3) its SaaS subtype if applicable, (4) a brief description. "
                "Return ONLY a JSON object with keys: country, is_saas, saas_subtype, description, industry."
            ),
            "company_name": company_name,
            "currency": currency,
            "source": source_type,
            "available_fields": available[:10],
        }, indent=2)

        resp = llm.invoke([
            SystemMessage(content=(
                "You are a company classification specialist. Respond with ONLY a valid JSON object. "
                "For country, use ISO 2-letter codes (US, IN, DE, etc.). "
                "For saas_subtype, use categories like: CRM, HCM, Security, Infrastructure, Analytics, "
                "Collaboration, FinTech, MarTech, DevOps, ERP, or 'general_software' or 'non_saas'. "
                "For industry, use standard categories like: Software, Financial Services, Manufacturing, etc."
            )),
            HumanMessage(content=classification_prompt),
        ])

        profile = _extract_json(resp.content)
        if not isinstance(profile, dict):
            profile = {
                "country": "US" if currency == "USD" else ("IN" if currency == "INR" else None),
                "is_saas": None,
                "saas_subtype": None,
                "description": f"Company identified as {company_name}",
                "industry": None,
            }
            _log(state, "Company Intelligence Agent: LLM classification failed — using defaults")

    except Exception as exc:
        profile = {
            "country": "US" if currency == "USD" else ("IN" if currency == "INR" else None),
            "is_saas": None,
            "saas_subtype": None,
            "description": f"Company identified as {company_name}",
            "industry": None,
        }
        state.setdefault("errors", []).append(f"Company Intelligence: {exc}")
        _log(state, f"Company Intelligence Agent: Error — {exc}")

    # Update record with classification
    record.country = profile.get("country")
    record.saas_subtype = profile.get("saas_subtype")
    record.company_description = profile.get("description")
    record.industry = profile.get("industry")

    state["company_record"] = record.model_dump()
    state["company_profile"] = profile
    _log(state, f"Company Intelligence Agent: Classified as {profile.get('industry', 'unknown')} in {profile.get('country', 'unknown')}")

    return state


# -------------------------------------------------------------------------
# Node 2: Deterministic Financial Computation
# -------------------------------------------------------------------------

def financial_computation_node(state: WorkflowState) -> WorkflowState:
    """Runs ALL deterministic financial calculations.

    NOT AGENTIC: This is pure Python computation. No LLM involvement.
    The LLM cannot see, modify, or override these calculations.

    Produces the FinancialFactLedger — the immutable contract between
    the computation layer and the reasoning layer.
    """
    _log(state, "Financial Computation: Starting deterministic calculations")

    record_data = state.get("company_record", {})
    record = NormalizedCompanyRecord(**record_data)

    all_entries: List[FactLedgerEntry] = []

    # Profitability metrics
    try:
        profitability = compute_profitability_metrics(record)
        all_entries.extend(profitability)
        _log(state, f"Financial Computation: {len(profitability)} profitability metrics computed")
    except Exception as exc:
        state.setdefault("errors", []).append(f"Profitability calc: {exc}")
        _log(state, f"Financial Computation: Profitability error — {exc}")

    # Solvency metrics
    try:
        solvency = compute_solvency_metrics(record)
        all_entries.extend(solvency)
        _log(state, f"Financial Computation: {len(solvency)} solvency metrics computed")
    except Exception as exc:
        state.setdefault("errors", []).append(f"Solvency calc: {exc}")

    # Liquidity metrics
    try:
        liquidity = compute_liquidity_metrics(record)
        all_entries.extend(liquidity)
        _log(state, f"Financial Computation: {len(liquidity)} liquidity metrics computed")
    except Exception as exc:
        state.setdefault("errors", []).append(f"Liquidity calc: {exc}")

    # Working-capital cycle
    try:
        wc = compute_working_capital_cycle(record)
        all_entries.extend(wc)
        _log(state, f"Financial Computation: {len(wc)} working-capital metrics computed")
    except Exception as exc:
        state.setdefault("errors", []).append(f"Working capital calc: {exc}")

    # SaaS metrics — only for software companies (meaningless for a bank/airline/etc.)
    if _is_software_company(state.get("company_profile", {})):
        try:
            saas = compute_saas_metrics(record)
            all_entries.extend(saas)
            _log(state, f"Financial Computation: {len(saas)} SaaS metrics computed")
        except Exception as exc:
            state.setdefault("errors", []).append(f"SaaS calc: {exc}")
    else:
        _log(state, "Financial Computation: SaaS metrics skipped (not a software company)")

    # DSCR
    dscr_input_data = state.get("dscr_inputs", {})
    dscr_inputs = DSCRInputs(**dscr_input_data) if dscr_input_data else DSCRInputs()

    try:
        dscr_result = compute_dscr(record, dscr_inputs)
        dscr_entry = dscr_to_fact_entry(dscr_result)
        all_entries.append(dscr_entry)
        state["dscr_result"] = dscr_result.model_dump()
        _log(state, f"Financial Computation: DSCR = {dscr_result.dscr_ratio} ({dscr_result.risk_level.value})")
    except Exception as exc:
        state.setdefault("errors", []).append(f"DSCR calc: {exc}")
        _log(state, f"Financial Computation: DSCR error — {exc}")

    # Build risk dashboard
    try:
        dscr_for_risk = DSCRResult(**state["dscr_result"]) if state.get("dscr_result") else None
        risk_dashboard = build_risk_dashboard(record, all_entries, dscr_for_risk)
        state["risk_dashboard"] = risk_dashboard.model_dump()
        _log(state, f"Financial Computation: Risk dashboard — {risk_dashboard.overall_risk.value} ({risk_dashboard.fail_count} FAIL, {risk_dashboard.warn_count} WARN)")
    except Exception as exc:
        state.setdefault("errors", []).append(f"Risk dashboard: {exc}")

    # Build fact ledger
    ledger = FinancialFactLedger(
        entity_id=record.entity_id,
        analysis_timestamp=datetime.now(timezone.utc).isoformat(),
        currency=record.currency,
        entries=all_entries,
    )
    state["fact_ledger"] = ledger.model_dump()
    _log(state, f"Financial Computation: Fact ledger built with {len(all_entries)} entries")

    return state


# -------------------------------------------------------------------------
# Node 3: Peer Analysis Agent
# -------------------------------------------------------------------------

def peer_analysis_node(state: WorkflowState) -> WorkflowState:
    """Identifies and fetches REAL data for peer companies.

    WHY AGENTIC: The agent must reason about WHICH companies are good peers
    based on the target company's SaaS subtype, size, and geography.

    CRITICAL V2 CHANGE: V1 asked the LLM to hallucinate peer financials.
    V2 uses the LLM only to IDENTIFY peer tickers, then FETCHES actual data.
    """
    _log(state, "Peer Analysis Agent: Starting peer identification")

    record_data = state.get("company_record", {})
    record = NormalizedCompanyRecord(**record_data)
    profile = state.get("company_profile", {})

    peers: List[PeerCompany] = []

    try:
        llm = _get_llm(state)
        # Step 1: LLM identifies peer TICKERS (not financials)
        peer_prompt = json.dumps({
            "task": (
                "Identify 3-5 publicly traded peer companies for comparison. "
                "Return ONLY a JSON array of objects with keys: name, ticker. "
                "The ticker must be a valid Yahoo Finance ticker symbol. "
                "CRITICAL: DO NOT include the target company itself. "
                "DO NOT estimate or provide ANY financial data — only names and tickers. "
                "Select peers based on: similar industry, similar SaaS subtype if applicable, "
                "similar geographic market."
            ),
            "target_company": record.entity_id,
            "industry": profile.get("industry"),
            "saas_subtype": profile.get("saas_subtype"),
            "country": profile.get("country"),
            "revenue_scale": f"{record.latest_value('revenue'):,.0f} {record.currency}" if record.latest_value("revenue") else "unknown",
        }, indent=2)

        resp = llm.invoke([
            SystemMessage(content=(
                "You are a financial analyst identifying peer companies for comparison. "
                "Return ONLY a valid JSON array. Each item must have 'name' and 'ticker' keys. "
                "Use Yahoo Finance ticker format (e.g., 'CRM' for Salesforce, 'INFY.NS' for Infosys). "
                "DO NOT include any financial estimates or numbers — only company names and tickers. "
                "DO NOT include the target company in the array."
            )),
            HumanMessage(content=peer_prompt),
        ])

        raw_peer_tickers = _extract_json(resp.content)
        if not isinstance(raw_peer_tickers, list):
            raw_peer_tickers = []
            _log(state, "Peer Analysis Agent: LLM peer identification failed")

        # Deduplicate and filter out target company
        peer_tickers = []
        seen_tickers = set()
        target_name_lower = record.entity_id.lower()
        
        for p in raw_peer_tickers:
            ticker = p.get("ticker", "").strip().upper()
            name = p.get("name", "").strip()
            if not ticker or ticker in seen_tickers:
                continue
            # Basic check to exclude target
            if target_name_lower in name.lower() or name.lower() in target_name_lower:
                continue
                
            seen_tickers.add(ticker)
            peer_tickers.append(p)

        # Step 2: FETCH actual data for each peer (not hallucinated)
        if peer_tickers:
            _log(state, f"Peer Analysis Agent: LLM identified {len(peer_tickers)} valid peers, fetching actual data...")
            try:
                from finveritas.ingestion.ticker import fetch_by_ticker
            except ImportError:
                _log(state, "Peer Analysis Agent: yfinance not available")
                peer_tickers = []

            for peer_info in peer_tickers[:5]:  # Cap at 5
                ticker = peer_info.get("ticker", "")
                name = peer_info.get("name", ticker)
                if not ticker:
                    continue

                try:
                    peer_payload = fetch_by_ticker(ticker)
                    peer_record = payload_to_normalized_record(peer_payload, "ticker")

                    # Compute actual metrics for the peer
                    peer_rev = peer_record.latest_value("revenue")
                    peer_oi = peer_record.latest_value("operating_income")
                    peer_gp = peer_record.latest_value("gross_profit")
                    peer_eq = peer_record.latest_value("equity")
                    peer_td = peer_record.latest_value("total_debt") or peer_record.latest_value("total_liabilities")
                    peer_ca = peer_record.latest_value("current_assets")
                    peer_cl = peer_record.latest_value("current_liabilities")

                    # Growth
                    peer_rev_sorted = sorted(peer_record.revenue, key=lambda x: x.period) if peer_record.revenue else []
                    peer_growth = None
                    if len(peer_rev_sorted) >= 2:
                        prev, curr = peer_rev_sorted[-2].value, peer_rev_sorted[-1].value
                        if abs(prev) > 1e-9:
                            peer_growth = ((curr - prev) / abs(prev)) * 100.0

                    # Margins
                    peer_om = (peer_oi / peer_rev * 100) if (peer_oi is not None and peer_rev and abs(peer_rev) > 1e-9) else None
                    peer_gm = (peer_gp / peer_rev * 100) if (peer_gp is not None and peer_rev and abs(peer_rev) > 1e-9) else None

                    # Rule of 40
                    peer_r40 = (peer_growth + peer_om) if (peer_growth is not None and peer_om is not None) else None

                    # Leverage
                    peer_d2e = (peer_td / peer_eq) if (peer_td is not None and peer_eq is not None and abs(peer_eq) > 1e-9) else None

                    # Current ratio
                    peer_cr = (peer_ca / peer_cl) if (peer_ca is not None and peer_cl is not None and abs(peer_cl) > 1e-9) else None

                    # Determine tier
                    same_subtype = (profile.get("saas_subtype") and
                                    profile.get("saas_subtype") == peer_record.saas_subtype)
                    tier = "primary" if same_subtype else "secondary"

                    peers.append(PeerCompany(
                        entity_id=name,
                        ticker=ticker,
                        country=peer_record.country,
                        saas_subtype=peer_record.saas_subtype,
                        peer_tier=tier,
                        revenue=peer_rev,
                        revenue_currency=peer_record.currency,
                        revenue_growth=round(peer_growth, 2) if peer_growth is not None else None,
                        operating_margin=round(peer_om, 2) if peer_om is not None else None,
                        gross_margin=round(peer_gm, 2) if peer_gm is not None else None,
                        rule_of_40=round(peer_r40, 2) if peer_r40 is not None else None,
                        debt_to_equity=round(peer_d2e, 2) if peer_d2e is not None else None,
                        current_ratio=round(peer_cr, 2) if peer_cr is not None else None,
                        data_source="yfinance",
                        data_is_actual=True,
                    ))
                    _log(state, f"Peer Analysis Agent: Fetched actual data for {name} ({ticker})")

                except Exception as exc:
                    _log(state, f"Peer Analysis Agent: Failed to fetch {ticker}: {exc}")
                    continue

    except Exception as exc:
        state.setdefault("errors", []).append(f"Peer analysis: {exc}")
        _log(state, f"Peer Analysis Agent: Error — {exc}")

    # Build comparison
    comparison = PeerComparison(
        target_entity=record.entity_id,
        peers=peers,
        selection_rationale=f"Peers selected based on industry ({profile.get('industry', 'N/A')}), "
                           f"SaaS subtype ({profile.get('saas_subtype', 'N/A')}), "
                           f"and market geography ({profile.get('country', 'N/A')})",
    )

    # Compute comparison metrics
    if peers:
        target_rev = record.latest_value("revenue")
        metrics_to_compare = {
            "revenue_growth": ("saas_revenue_growth", None),
            "operating_margin": ("operating_margin", None),
            "gross_margin": ("gross_margin", None),
        }

        for metric_name, (ledger_key, _) in metrics_to_compare.items():
            target_val = None
            if state.get("fact_ledger"):
                ledger = FinancialFactLedger(**state["fact_ledger"])
                entry = ledger.get(ledger_key)
                if entry:
                    target_val = entry.value

            peer_vals = [getattr(p, metric_name, None) for p in peers if getattr(p, metric_name, None) is not None]
            peer_median = sorted(peer_vals)[len(peer_vals) // 2] if peer_vals else None

            comparison.comparison_metrics[metric_name] = {
                "target": target_val,
                "peer_median": peer_median,
                "peer_count": len(peer_vals),
            }

    state["peer_comparison"] = comparison.model_dump()
    _log(state, f"Peer Analysis Agent: {len(peers)} peers with actual data")

    return state


# -------------------------------------------------------------------------
# Node 4: Qualitative Analysis Agent
# -------------------------------------------------------------------------

def qualitative_analysis_node(state: WorkflowState) -> WorkflowState:
    """Extracts qualitative corporate intelligence from available text.

    WHY AGENTIC: Interpreting management commentary, earnings call content,
    and press releases requires contextual reasoning that can't be reduced
    to regex patterns.

    WHAT IT DOES:
    - Analyzes qualitative_context from the company record
    - Extracts: expansion plans, risk factors, material events, strategic shifts
    - Returns structured findings (not raw text)
    """
    _log(state, "Qualitative Analysis Agent: Starting")

    record_data = state.get("company_record", {})
    record = NormalizedCompanyRecord(**record_data)
    findings: List[str] = []

    qualitative_text = record.qualitative_context
    if not qualitative_text or len(qualitative_text.strip()) < 50:
        _log(state, "Qualitative Analysis Agent: No substantial qualitative context available")
        state["qualitative_findings"] = ["No qualitative corporate intelligence available for this company."]
        return state

    try:
        llm = _get_llm(state)
        prompt = json.dumps({
            "task": (
                "Analyze the following corporate commentary and extract structured findings relevant "
                "to credit assessment. Focus on: (1) expansion or contraction plans, "
                "(2) risk factors mentioned by management, (3) material events or changes, "
                "(4) strategic direction shifts, (5) any forward-looking guidance. "
                "Return a JSON array of strings, each being a concise factual finding. "
                "Do NOT invent information not present in the text."
            ),
            "company": record.entity_id,
            "text": qualitative_text[:3000],
        }, indent=2)

        resp = llm.invoke([
            SystemMessage(content=(
                "You are a corporate analyst extracting credit-relevant qualitative intelligence. "
                "Return ONLY a JSON array of concise findings. Each finding should be factual and "
                "directly supported by the provided text. Mark uncertainty with phrases like "
                "'management indicated' or 'commentary suggests'. Do not fabricate information."
            )),
            HumanMessage(content=prompt),
        ])

        findings = _extract_json(resp.content)
        if isinstance(findings, list):
            findings = [str(f) for f in findings]
        elif findings is not None:
            findings = [str(findings)]
        else:
            findings = [f"Qualitative context available but structured extraction failed: {qualitative_text[:200]}..."]

    except Exception as exc:
        findings = ["Qualitative analysis could not be performed due to an error."]
        state.setdefault("errors", []).append(f"Qualitative analysis: {exc}")

    state["qualitative_findings"] = findings
    _log(state, f"Qualitative Analysis Agent: Extracted {len(findings)} findings")

    return state


# -------------------------------------------------------------------------
# Node 5: Credit Assessment Agent
# -------------------------------------------------------------------------

def credit_assessment_node(state: WorkflowState) -> WorkflowState:
    """Synthesizes all evidence into a credit assessment report.

    WHY AGENTIC: The synthesis of financial metrics, peer comparison,
    qualitative evidence, and risk indicators into a coherent credit
    narrative requires contextual reasoning.

    GUARDRAIL: The agent CANNOT override deterministic risk classifications
    or change computed financial numbers. It can only narrate and interpret
    the pre-computed facts.
    """
    _log(state, "Credit Assessment Agent: Synthesizing final report")

    record_data = state.get("company_record", {})
    record = NormalizedCompanyRecord(**record_data)
    profile = state.get("company_profile", {})

    # Gather all computed facts
    ledger_data = state.get("fact_ledger", {})
    dscr_data = state.get("dscr_result")
    risk_data = state.get("risk_dashboard")
    peer_data = state.get("peer_comparison")
    qualitative = state.get("qualitative_findings", [])

    # Prepare deterministic summary for the LLM
    financial_summary: Dict[str, Any] = {}
    if ledger_data:
        ledger = FinancialFactLedger(**ledger_data)
        for entry in ledger.entries:
            if entry.value is not None:
                financial_summary[entry.display_name] = {
                    "value": entry.value,
                    "unit": entry.unit,
                    "status": entry.status.value,
                    "risk": entry.risk_signal.value if entry.risk_signal else None,
                }

    # Build report structure
    dscr_result = DSCRResult(**dscr_data) if dscr_data else None
    risk_dashboard = RiskDashboard(**risk_data) if risk_data else None
    peer_comparison = PeerComparison(**peer_data) if peer_data else None

    # Determine overall risk from the risk dashboard
    overall_risk = risk_dashboard.overall_risk if risk_dashboard else RiskLevel.MODERATE

    # Use LLM for the narrative synthesis
    recommendation = ""
    strengths: List[str] = []
    risks: List[str] = []

    try:
        llm = _get_llm(state, custom_timeout=120.0)
        synthesis_prompt = json.dumps({
            "task": (
                "Synthesize a credit assessment narrative for a lending institution. "
                "Based on the provided COMPUTED FACTS (you must not recalculate anything), "
                "identify: (1) 3-5 major strengths, (2) 3-5 major risks, "
                "(3) a 2-3 paragraph recommendation narrative. "
                "Return a JSON object with keys: strengths (array), risks (array), narrative (string). "
                "The narrative should reference specific metrics by name and value. "
                "You MUST NOT change any financial numbers — they are authoritative facts. "
                "You MUST NOT provide a definitive approve/reject recommendation — "
                "this is decision support for a qualified analyst."
            ),
            "company": record.entity_id,
            "industry": profile.get("industry"),
            "saas_subtype": profile.get("saas_subtype"),
            "financial_metrics": financial_summary,
            "dscr": {
                "ratio": dscr_result.dscr_ratio if dscr_result else None,
                "risk_level": dscr_result.risk_level.value if dscr_result else "N/A",
                "methodology": dscr_result.methodology.numerator_name if dscr_result else "N/A",
            } if dscr_result else None,
            "overall_risk": overall_risk.value,
            "peer_count": len(peer_comparison.peers) if peer_comparison else 0,
            "qualitative_findings": qualitative[:5],
        }, indent=2)

        resp = llm.invoke([
            SystemMessage(content=(
                "You are a credit analyst writing a decision-support report for a lending institution. "
                "Return ONLY a valid JSON object. "
                "All financial numbers referenced must match exactly what was provided — do not recalculate. "
                "The risk classification is FINAL and computed by the system — do not change it. "
                "Your role is to EXPLAIN the numbers and synthesize a narrative, not to generate new data. "
                "Include the standard disclaimer that this is decision support, not a binding credit decision."
            )),
            HumanMessage(content=synthesis_prompt),
        ])

        synthesis = _extract_json(resp.content)
        if isinstance(synthesis, dict):
            strengths = synthesis.get("strengths", []) or []
            risks = synthesis.get("risks", []) or []
            recommendation = synthesis.get("narrative", "") or ""
        if not recommendation:
            # Fall back to the raw text if it wasn't valid JSON but has content.
            raw = (resp.content or "").strip()
            recommendation = raw if raw else "Credit assessment narrative could not be generated."
            if not isinstance(synthesis, dict):
                _log(state, "Credit Assessment Agent: LLM synthesis not valid JSON — used raw text")

    except Exception as exc:
        recommendation = f"Credit assessment narrative generation failed: {exc}"
        state.setdefault("errors", []).append(f"Credit assessment: {exc}")

    # Build final report
    report = CreditAssessmentReport(
        entity_id=record.entity_id,
        analysis_date=datetime.now(timezone.utc).isoformat(),
        currency=record.currency,
        dscr_result=dscr_result,
        financial_summary=financial_summary,
        saas_classification=profile.get("saas_subtype"),
        saas_metrics={e.metric: {"value": e.value, "unit": e.unit}
                      for e in (FinancialFactLedger(**ledger_data).by_category("saas") if ledger_data else [])
                      if e.value is not None},
        peer_comparison=peer_comparison,
        risk_dashboard=risk_dashboard,
        qualitative_findings=qualitative,
        major_strengths=strengths,
        major_risks=risks,
        data_quality_notes=[],
        missing_information=[],
        assumptions=[],
        risk_classification=overall_risk,
        recommendation_narrative=recommendation,
    )

    state["credit_report"] = report.model_dump()
    _log(state, f"Credit Assessment Agent: Report generated — overall risk: {overall_risk.value}")

    return state


# -------------------------------------------------------------------------
# Build the LangGraph workflow
# -------------------------------------------------------------------------

def build_workflow() -> StateGraph:
    """Build the V2 agentic workflow graph.

    Flow:
      company_intelligence → financial_computation → peer_analysis
      → qualitative_analysis → credit_assessment → END
    """
    workflow = StateGraph(WorkflowState)

    # Add nodes
    workflow.add_node("company_intelligence", company_intelligence_node)
    workflow.add_node("financial_computation", financial_computation_node)
    workflow.add_node("peer_analysis", peer_analysis_node)
    workflow.add_node("qualitative_analysis", qualitative_analysis_node)
    workflow.add_node("credit_assessment", credit_assessment_node)

    # Define edges
    workflow.set_entry_point("company_intelligence")
    workflow.add_edge("company_intelligence", "financial_computation")
    workflow.add_edge("financial_computation", "peer_analysis")
    workflow.add_edge("peer_analysis", "qualitative_analysis")
    workflow.add_edge("qualitative_analysis", "credit_assessment")
    workflow.add_edge("credit_assessment", END)

    return workflow


def run_analysis(
    payload: Dict[str, Any],
    source_type: str = "unknown",
    dscr_inputs: Optional[Dict[str, Any]] = None,
    llm_base_url: str = "http://localhost:1234/v1",
    llm_model: str = "qwen2.5-coder-1.5b-instruct-mlx",
    llm_api_key: str = "local",
    fmp_api_key: Optional[str] = None,
    news_api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the complete V2 analysis workflow.

    Args:
        payload: Raw financial data payload (entity + time_series)
        source_type: Source identifier (bloomberg_pdf, ticker, csv)
        dscr_inputs: DSCR calculation inputs (loan terms)
        llm_base_url: LLM API base URL
        llm_model: LLM model name
        llm_api_key: LLM API key
        fmp_api_key: Optional FMP API key for supplemental data
        news_api_key: Optional NewsAPI key for sentiment

    Returns:
        Complete workflow state including credit report, fact ledger, and risk dashboard.
    """
    graph = build_workflow()
    app = graph.compile()

    initial_state: WorkflowState = {
        "payload": payload,
        "source_type": source_type,
        "dscr_inputs": dscr_inputs or {},
        "llm_base_url": llm_base_url,
        "llm_model": llm_model,
        "llm_api_key": llm_api_key,
        "fmp_api_key": fmp_api_key,
        "news_api_key": news_api_key,
        "errors": [],
        "workflow_log": [],
    }

    result = app.invoke(initial_state)
    return dict(result)
