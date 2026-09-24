"""Analysis views: Agent Workflow, Financial Analysis (all V3 sections), and Basel pages.
Rendered after an analysis has been run."""
from __future__ import annotations

from __future__ import annotations

import traceback
import html
from typing import Any

import pandas as pd
import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from analysis.agents.agent_workflow import run_analysis
from ingestion.payload_mapper import payload_to_normalized_record
from shared.schema import DSCRInputs, NormalizedCompanyRecord
from analysis.engines.debt_service import LoanTerms, compute_dscr_schedule
from analysis.engines.credit_scorecard import compute_scorecard
from analysis.engines.credit_memo import build_memo, render_memo_html
from analysis.engines.forecast import forecast_field
from analysis.agents.ai_assistant import explain_results, answer_question
from analysis.engines.anomaly_engine import detect_anomalies
from shared.metric_meanings import meaning_for
from ingestion.scale_detection import rescale_payload
from shared.formatting import format_money, format_ratio, format_percent
from ingestion.pdf.pdf_parser import parse_pdf_to_json, payload_to_agent_files
from ingestion.yfinance_ingestion import fetch_by_ticker
from ingestion.private_company_ingestion import load_private_company_data, get_template_csv
from ingestion.supplemental_fetchers import auto_fetch_missing_fields
from ingestion.data_verifier import run_verification, CredibilityReport, STATUS_PASS, STATUS_WARN, STATUS_FAIL, STATUS_SKIP
from shared.components import (
    agent_tooltip_html,
    inject_theme_vars,
    load_css,
    render_agent_card,
    render_cross_ref_card,
    render_hr,
    render_metric_cards,
    render_section_header,
    render_top_bar,
)
from auth.auth_controller import decode_token
from auth.ui_pages import page_login, page_register, page_forgot_password, page_history
from auth.db import get_file_history, make_history_doc

import os
from dotenv import load_dotenv

load_dotenv()


def page_workflow() -> None:
    render_section_header("Agent Pipeline Architecture", subtitle="Hover over nodes to inspect outputs")

    outputs = st.session_state.get("agent_outputs") or {}
    if not outputs:
        if not st.session_state.get("ocr_cache"):
            st.warning("⚠️ Please ingest data first by using the **Upload Statement** page.")
        else:
            st.warning("⚠️ No financial analysis done, hence no workflow generated. Please click **RUN FULL ANALYSIS** on the Upload page.")
        return

    st.markdown("""
        <div class="bb-workflow-legend">
            <div class="bb-legend-item"><span class="bb-legend-dot" style="background:#4A4A5A"></span>I/O Nodes</div>
            <div class="bb-legend-item"><span class="bb-legend-dot" style="background:#0D3B66"></span>OCR Parser</div>
            <div class="bb-legend-item"><span class="bb-legend-dot" style="background:#3B2800"></span>Deterministic Engines</div>
            <div class="bb-legend-item"><span class="bb-legend-dot" style="background:#003040"></span>Data Sufficiency (LangGraph)</div>
            <div class="bb-legend-item"><span class="bb-legend-dot" style="background:#002010"></span>DSCR / Credit Assessment</div>
        </div>""", unsafe_allow_html=True)

    nodes = [
        # ── Data sources (3 paths) ──────────────────────────────────────────
        Node(id="pdf",    label="Bloomberg\nPDF",          color="#1A1A2E", shape="box",     size=20, font={"color":"#CCCCCC","size":12}),
        Node(id="ticker", label="Ticker\n(yfinance)",       color="#1A1A2E", shape="box",     size=20, font={"color":"#00BFFF","size":12}),
        Node(id="csv",    label="Private Co.\nCSV/Excel",   color="#1A1A2E", shape="box",     size=20, font={"color":"#FFB000","size":12}),
        # ── Ingestion / Schema converter ────────────────────────────────────
        Node(id="ingest", label="Normalization\nLayer",         color="#0D3B66", shape="box",     size=22, font={"color":"#00BFFF","size":12}),
        # ── Deterministic agents ─────────────────────────────────────────────
        Node(id="rev",    label="Revenue\nCalculator",      color="#3B2800", shape="ellipse", size=22, font={"color":"#FFB000","size":12}),
        Node(id="liq",    label="Liquidity\nCalculator",    color="#3B2800", shape="ellipse", size=22, font={"color":"#00BFFF","size":12}),
        Node(id="bs",     label="Balance Sheet\nCalculator",color="#3B2800", shape="ellipse", size=22, font={"color":"#FF6B35","size":12}),
        Node(id="saas",   label="SaaS Rule of 40\nEngine",  color="#3B2800", shape="ellipse", size=22, font={"color":"#CC88FF","size":12}),
        # ── LangGraph Workflow ────────────────────────────────────────────────────
        Node(id="data_suf",label="Data Sufficiency\nAgent",  color="#003040", shape="box",     size=24, font={"color":"#00FF88","size":12}),
        Node(id="dscr",   label="DSCR\nCalculator",         color="#002010", shape="box",     size=20, font={"color":"#E6E6E6","size":12}),
    ]
    edges = [
        Edge(source="pdf",    target="ingest", color="#555566", width=2),
        Edge(source="ticker", target="ingest", color="#00BFFF", width=2),
        Edge(source="csv",    target="ingest", color="#FFB000", width=2),
        Edge(source="ingest", target="rev",    color="#FFB000", width=1),
        Edge(source="ingest", target="liq",    color="#00BFFF", width=1),
        Edge(source="ingest", target="bs",     color="#FF6B35", width=1),
        Edge(source="ingest", target="saas",   color="#CC88FF", width=1),
        
        Edge(source="ingest", target="data_suf", color="#FFFFFF", width=2),
        Edge(source="data_suf", target="dscr",   color="#00FF88", width=2, label="If Data Sufficient"),
    ]
    config = Config(width="100%", height=520, directed=True, physics=False, hierarchical=True,
                    hierarchical_sort_method="directed", nodeHighlightBehavior=True, highlightColor="#FFB000", collapsible=False)
    agraph(nodes=nodes, edges=edges, config=config)

    render_hr()
    if outputs:
        render_section_header("Agent Transparency & Guardrails", subtitle="Active constraints and system rules enforced during execution")
        
        guardrails_html = """
        <div style="background:#070809;border:1px solid #1E2030;border-left:4px solid #D4963A;padding:20px;border-radius:4px;">
            <div style="display:flex;margin-bottom:16px;border-bottom:1px solid #1A1C23;padding-bottom:14px;">
                <div style="width:200px;font-size:12px;color:#FFB000;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;font-family:'JetBrains Mono',monospace;">Revenue Agent</div>
                <div style="flex:1;font-size:13px;color:#9A9AB0;font-family:'Inter',sans-serif;line-height:1.6;">
                    <strong style="color:#D8D8E0;">Deterministic Math Lock:</strong> Hardcoded to compute CAGR, volatility, and YoY growth via strict pandas formulas. LLM routing is disabled for metric calculations to prevent numeric hallucination.
                </div>
            </div>
            <div style="display:flex;margin-bottom:16px;border-bottom:1px solid #1A1C23;padding-bottom:14px;">
                <div style="width:200px;font-size:12px;color:#00BFFF;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;font-family:'JetBrains Mono',monospace;">Liquidity Agent</div>
                <div style="flex:1;font-size:13px;color:#9A9AB0;font-family:'Inter',sans-serif;line-height:1.6;">
                    <strong style="color:#D8D8E0;">Restricted Output Schema:</strong> Output is strictly forced into an ISO formatting schema. Evaluates Working Capital using a standardized threshold algorithm before summarization.
                </div>
            </div>
            <div style="display:flex;margin-bottom:16px;border-bottom:1px solid #1A1C23;padding-bottom:14px;">
                <div style="width:200px;font-size:12px;color:#FF6B35;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;font-family:'JetBrains Mono',monospace;">Balance Sheet Agent</div>
                <div style="flex:1;font-size:13px;color:#9A9AB0;font-family:'Inter',sans-serif;line-height:1.6;">
                    <strong style="color:#D8D8E0;">Accounting Integrity Check:</strong> Enforces the fundamental accounting identity (Assets ≈ Liabilities + Equity). Rejects unstructured estimations.
                </div>
            </div>
            <div style="display:flex;margin-bottom:16px;border-bottom:1px solid #1A1C23;padding-bottom:14px;">
                <div style="width:200px;font-size:12px;color:#CC88FF;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;font-family:'JetBrains Mono',monospace;">Debt Service &amp; Scorecard</div>
                <div style="flex:1;font-size:13px;color:#9A9AB0;font-family:'Inter',sans-serif;line-height:1.6;">
                    <strong style="color:#D8D8E0;">Deterministic Underwriting:</strong> Builds the year-by-year DSCR schedule, stress tests, and the industry-aware credit grade in pure Python. The LLM never sets a ratio, grade, or default probability.
                </div>
            </div>
            <div style="display:flex;">
                <div style="width:200px;font-size:12px;color:#00FF88;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;font-family:'JetBrains Mono',monospace;">Cross-Reference</div>
                <div style="flex:1;font-size:13px;color:#9A9AB0;font-family:'Inter',sans-serif;line-height:1.6;">
                    <strong style="color:#D8D8E0;">Synthesis Engine:</strong> Aggregates deterministic metrics from all prior agents to generate a unified financial narrative. Strictly prohibited from injecting new numbers, calculating secondary metrics, or offering credit/lending decisions.
                </div>
            </div>
        </div>
        """
        st.markdown(guardrails_html, unsafe_allow_html=True)
        
    else:
        st.markdown('<div style="color:#444;font-size:11px;margin-top:12px;">▸ Run analysis on the Upload page to view agent constraints.</div>', unsafe_allow_html=True)


_RISK_COLORS = {"LOW": "#00FF88", "MODERATE": "#FFB000", "HIGH": "#FF6B35", "CRITICAL": "#FF3333", "INSUFFICIENT_DATA": "#888"}


def _render_debt_serviceability_v3(workflow_state: dict[str, Any]) -> None:
    """V3 interactive DSCR: amortization schedule, per-year & minimum DSCR, stress tests."""
    render_hr()
    render_section_header(
        "Debt Serviceability Analysis",
        subtitle="V3 · DSCR across the full loan life, with stress testing",
    )

    record_data = workflow_state.get("company_record")
    if not record_data:
        st.info("Run an analysis first — this section needs the company's financial record.")
        return

    try:
        record = NormalizedCompanyRecord(**record_data)
    except Exception as exc:
        st.warning(f"Could not read company record for debt-service analysis: {exc}")
        return

    ccy = record.currency

    # Which numerator bases can we actually compute from the available data?
    have = {
        "ebitda": record.has_field("ebitda"),
        "ebit": record.has_field("operating_income"),
        "ocf": record.has_field("operating_cash_flow"),
        "cfads": record.has_field("operating_cash_flow"),
    }
    basis_labels = {
        "cfads": "CFADS — OCF + interest − capex (most conservative)",
        "ocf": "Operating Cash Flow (+ interest add-back)",
        "ebitda": "EBITDA (earnings proxy)",
        "ebit": "EBIT / Operating Income",
    }
    available_bases = [b for b in ("cfads", "ocf", "ebitda", "ebit") if have[b]]

    st.markdown(
        '<p style="font-size:12px;color:#7A7D96;line-height:1.6;">'
        "Enter the proposed loan terms. We build a year-by-year repayment schedule, compute the "
        "<b>DSCR for every year</b>, and report the <b>minimum</b> (the tightest year — what a lender "
        "underwrites against) plus how it holds up under stress.</p>",
        unsafe_allow_html=True,
    )

    if not available_bases:
        st.warning(
            "No cash-flow basis available for DSCR (need EBITDA, Operating Income, or Operating Cash Flow). "
            "Try a listed ticker, which includes the cash-flow statement."
        )
        return

    with st.form("v3_dscr_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            principal = st.number_input(f"Loan Amount ({ccy or 'currency'})", min_value=0.0, value=0.0, step=1000.0, key="v3_principal")
            rate = st.number_input("Interest Rate (% p.a.)", min_value=0.0, max_value=100.0, value=10.0, step=0.25, key="v3_rate")
        with c2:
            tenure = st.number_input("Tenure (years)", min_value=1, max_value=40, value=5, step=1, key="v3_tenure")
            structure = st.selectbox("Repayment Structure", ["equal_installment", "bullet", "balloon"], key="v3_structure")
        with c3:
            moratorium = st.number_input("Moratorium (years, interest-only)", min_value=0, max_value=10, value=0, step=1, key="v3_moratorium")
            basis = st.selectbox("Cash basis (numerator)", available_bases,
                                 format_func=lambda b: basis_labels[b], key="v3_basis")
        existing_ds = st.number_input(f"Existing annual debt service ({ccy or 'currency'})", min_value=0.0, value=0.0, step=1000.0, key="v3_existing_ds")
        submitted = st.form_submit_button("Compute Debt Serviceability", use_container_width=True)

    if submitted:
        st.session_state["v3_dscr_terms"] = {
            "principal": principal, "annual_rate_pct": rate, "tenure_years": int(tenure),
            "structure": structure, "moratorium_years": int(moratorium),
            "existing_annual_debt_service": existing_ds, "basis": basis,
        }

    terms_dict = st.session_state.get("v3_dscr_terms")
    if not terms_dict:
        return
    if terms_dict.get("principal", 0) <= 0:
        st.info("Enter a loan amount above and click Compute.")
        return

    basis = terms_dict.get("basis", "cfads")
    loan_kwargs = {k: v for k, v in terms_dict.items() if k != "basis"}
    terms = LoanTerms(**loan_kwargs)
    result = compute_dscr_schedule(record, terms, basis=basis)
    # Persist min DSCR so the credit scorecard can factor in debt-service coverage.
    st.session_state["v3_min_dscr"] = result.min_dscr

    if result.min_dscr is None:
        st.warning("DSCR could not be computed with the available data. " + " ".join(result.notes))
        return

    color = _RISK_COLORS.get(result.risk_level.value, "#888")

    # ── Headline ──────────────────────────────────────────────────────────
    h1, h2, h3, h4 = st.columns(4)
    h1.markdown(
        f'<div style="text-align:center;"><div style="font-size:11px;color:#7A7D96;">MINIMUM DSCR</div>'
        f'<div style="font-size:32px;font-weight:bold;color:{color};">{result.min_dscr:.2f}x</div>'
        f'<div style="font-size:10px;color:#7A7D96;">worst year: Y{result.min_dscr_year}</div></div>',
        unsafe_allow_html=True,
    )
    h2.markdown(
        f'<div style="text-align:center;"><div style="font-size:11px;color:#7A7D96;">AVERAGE DSCR</div>'
        f'<div style="font-size:32px;font-weight:bold;color:#E6E6E6;">{result.avg_dscr:.2f}x</div>'
        f'<div style="font-size:10px;color:#7A7D96;">over {terms.tenure_years} years</div></div>',
        unsafe_allow_html=True,
    )
    h3.markdown(
        f'<div style="text-align:center;"><div style="font-size:11px;color:#7A7D96;">RISK LEVEL</div>'
        f'<div style="font-size:22px;font-weight:bold;color:{color};margin-top:6px;">{result.risk_level.value}</div></div>',
        unsafe_allow_html=True,
    )
    h4.markdown(
        f'<div style="text-align:center;"><div style="font-size:11px;color:#7A7D96;">CASH BASIS</div>'
        f'<div style="font-size:15px;font-weight:bold;color:#00BFFF;margin-top:8px;">{result.numerator_basis.upper()}</div>'
        f'<div style="font-size:11px;color:#7A7D96;">{format_money(result.numerator_value, ccy)}/yr</div></div>',
        unsafe_allow_html=True,
    )

    # Plain-language read
    if result.min_dscr >= 1.5:
        verdict = f"Comfortable: even in its tightest year the borrower's cash covers debt service {result.min_dscr:.2f}×."
    elif result.min_dscr >= 1.0:
        verdict = f"Tight: in year {result.min_dscr_year} coverage falls to {result.min_dscr:.2f}× — little buffer."
    else:
        verdict = f"Shortfall: in year {result.min_dscr_year} cash covers only {result.min_dscr:.2f}× of debt service (below 1.0× = cannot fully pay)."
    st.markdown(
        f'<div style="font-size:13px;color:#D8D8E0;margin:14px 0;padding:12px;background:#0B0C10;border-left:3px solid {color};border-radius:3px;">{html.escape(verdict)}</div>',
        unsafe_allow_html=True,
    )

    # Coverage companions
    cov = []
    if result.interest_coverage is not None:
        cov.append(f"Interest Coverage: **{result.interest_coverage:.2f}x**")
    if result.debt_to_ebitda is not None:
        cov.append(f"Debt / EBITDA: **{result.debt_to_ebitda:.2f}x**")
    if cov:
        st.markdown('<span style="font-size:12px;color:#7A7D96;">Companion coverage — </span>' + " · ".join(cov))

    # ── DSCR by year chart ────────────────────────────────────────────────
    chart_col, tbl_col = st.columns([1, 1])
    with chart_col:
        st.markdown("**DSCR by year**")
        df_chart = pd.DataFrame(
            {"DSCR": [d for d in result.dscr_by_year]},
            index=[f"Y{r.year}" for r in result.schedule],
        )
        st.line_chart(df_chart, height=220)
        st.caption("The 1.0× line is the danger threshold — below it, that year's cash can't cover debt service.")

    with tbl_col:
        st.markdown("**Amortization schedule**")
        rows = []
        for r, d in zip(result.schedule, result.dscr_by_year):
            rows.append({
                "Yr": r.year,
                "Principal": format_money(r.principal, ccy, decimals=1),
                "Interest": format_money(r.interest, ccy, decimals=1),
                "Payment": format_money(r.total_payment, ccy, decimals=1),
                "DSCR": f"{d:.2f}x" if d is not None else "—",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, height=220)

    # ── Stress tests ──────────────────────────────────────────────────────
    if result.stress_results:
        st.markdown("**Stress tests** — how the minimum DSCR holds up if things go wrong")
        srows = []
        for s in result.stress_results:
            srows.append({
                "Scenario": s.description,
                "Min DSCR": f"{s.min_dscr:.2f}x" if s.min_dscr is not None else "—",
                "Δ vs base": f"{s.delta_vs_base:+.2f}" if s.delta_vs_base is not None else "—",
                "Below 1.0x?": "⚠️ YES" if s.breaches_1x else "no",
            })
        st.dataframe(pd.DataFrame(srows), hide_index=True, use_container_width=True)
        breaches = [s for s in result.stress_results if s.breaches_1x]
        if breaches:
            st.markdown(
                f'<div style="font-size:12px;color:#FF6B35;padding:8px 12px;background:#1A0D00;border-radius:3px;">'
                f'⚠️ Coverage falls below 1.0× under {len(breaches)} stress scenario(s) — the borrower would struggle to repay if these occur.</div>',
                unsafe_allow_html=True,
            )

    # ── Methodology ───────────────────────────────────────────────────────
    with st.expander("DSCR Methodology & Assumptions"):
        st.markdown(f"- **Numerator (cash available):** {result.numerator_formula} = {format_money(result.numerator_value, ccy)}")
        st.markdown(f"- **Denominator:** scheduled principal + interest each year" + (f" + existing debt service {format_money(terms.existing_annual_debt_service, ccy)}" if terms.existing_annual_debt_service else ""))
        st.markdown(f"- **Structure:** {terms.structure}" + (f", {terms.moratorium_years}yr moratorium" if terms.moratorium_years else ""))
        st.markdown("- **Assumption:** annual cash held constant across the loan life (conservative — no growth assumed).")
        for n in result.notes:
            st.markdown(f"- ⚠️ {n}")


_GRADE_COLORS = {"AA": "#00FF88", "A": "#00FF88", "BBB": "#00BFFF", "BB": "#FFB000",
                 "B": "#FF6B35", "CCC": "#FF3333", "D": "#FF3333", "NR": "#888"}
_STATUS_COLORS = {"strong": "#00FF88", "ok": "#FFB000", "weak": "#FF3333", "missing": "#555"}


def _render_ledger_category(fact_ledger_data: Any, category: str, title: str) -> None:
    """Render one fact-ledger category as metric rows with meanings (currency-aware)."""
    if not fact_ledger_data:
        return
    entries = [e for e in fact_ledger_data.get("entries", []) if e.get("category") == category]
    if not entries:
        return
    out = f'<div class="bb-agent-card" style="margin-top:12px;"><div class="bb-agent-card-title">{html.escape(title)}</div>'
    for entry in entries:
        val = entry.get("value")
        name = entry.get("display_name", "")
        unit = entry.get("unit", "")
        risk = entry.get("risk_signal")
        color = "#E6E6E6"
        if risk == "PASS": color = "#00FF88"
        elif risk == "WARN": color = "#FFB000"
        elif risk == "FAIL": color = "#FF3333"
        if val is not None:
            if unit == "%":
                disp = f"{val:.2f}%"
            elif unit == "x":
                disp = f"{val:.2f}x"
            elif unit and unit.isupper() and len(unit) <= 4:
                disp = format_money(val, unit)   # currency-denominated (e.g. working capital)
            else:
                disp = f"{val:,.2f} {unit}".strip()
        else:
            disp, color = "N/A", "#666"
        out += (f'<div class="bb-metric-row"><span class="bb-mkey">{html.escape(name)}</span>'
                f'<span class="bb-mval" style="color:{color};">{html.escape(disp)}</span></div>')
        m = meaning_for(entry.get("metric"))
        if m:
            out += f'<div style="font-size:10px;color:#7A7D96;margin:-6px 0 8px 0;">{html.escape(m)}</div>'
    out += '</div>'
    st.markdown(out, unsafe_allow_html=True)


def _render_verdict_banner_v3(workflow_state: dict[str, Any]) -> None:
    """A one-line plain-language verdict at the very top of the results."""
    record_data = workflow_state.get("company_record")
    if not record_data:
        return
    try:
        record = NormalizedCompanyRecord(**record_data)
    except Exception:
        return

    profile = workflow_state.get("company_profile", {})
    industry = record.industry or profile.get("industry")
    min_dscr = st.session_state.get("v3_min_dscr")
    sc = compute_scorecard(record, industry=industry, min_dscr=min_dscr)

    if sc.composite_score is None:
        return

    color = _GRADE_COLORS.get(sc.grade, "#888")

    # Weakest scored factor = the headline watch item.
    scored = [f for f in sc.factors if f.score is not None]
    watch = min(scored, key=lambda f: f.score) if scored else None
    watch_txt = ""
    if watch and watch.score < 55:
        watch_txt = f" · <span style='color:#FF6B35;'>Watch: {html.escape(watch.name.lower())} ({html.escape(watch.note)})</span>"

    dscr_txt = ""
    if min_dscr is not None:
        dcol = "#00FF88" if min_dscr >= 1.5 else "#FFB000" if min_dscr >= 1.0 else "#FF3333"
        dscr_txt = f" · <span style='color:{dcol};'>Min DSCR {min_dscr:.2f}x</span>"

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:14px;padding:14px 18px;background:#0B0C10;'
        f'border:1px solid #1E2030;border-left:5px solid {color};border-radius:6px;margin-bottom:8px;">'
        f'<div style="font-size:26px;font-weight:800;color:{color};">{html.escape(sc.grade)}</div>'
        f'<div style="font-size:13px;color:#D8D8E0;line-height:1.5;">'
        f'<b style="color:{color};">{html.escape(sc.grade_label)}</b> · composite {sc.composite_score:.0f}/100'
        f'{dscr_txt}{watch_txt}<br>'
        f'<span style="font-size:11px;color:#7A7D96;">Decision-support only — not a lending decision. '
        f'Scroll for the full breakdown.</span></div></div>',
        unsafe_allow_html=True,
    )


def _render_credit_scorecard_v3(workflow_state: dict[str, Any]) -> None:
    """V3 credit scorecard: one industry-aware grade + PD with a transparent breakdown."""
    record_data = workflow_state.get("company_record")
    if not record_data:
        return
    try:
        record = NormalizedCompanyRecord(**record_data)
    except Exception:
        return

    profile = workflow_state.get("company_profile", {})
    industry = record.industry or profile.get("industry")
    min_dscr = st.session_state.get("v3_min_dscr")

    sc = compute_scorecard(record, industry=industry, min_dscr=min_dscr)

    render_section_header("Credit Scorecard", subtitle="V3 · one industry-aware grade, fully broken down")

    if sc.composite_score is None:
        st.info("Not enough financial data to score this company yet.")
        return

    color = _GRADE_COLORS.get(sc.grade, "#888")

    # ── Headline grade card ───────────────────────────────────────────────
    g1, g2 = st.columns([1, 2])
    with g1:
        st.markdown(
            f'<div style="text-align:center;padding:18px;background:#0B0C10;border:1px solid #1E2030;border-radius:6px;border-top:4px solid {color};">'
            f'<div style="font-size:11px;color:#7A7D96;letter-spacing:0.1em;">CREDIT GRADE</div>'
            f'<div style="font-size:52px;font-weight:800;color:{color};line-height:1.1;">{sc.grade}</div>'
            f'<div style="font-size:12px;color:#D8D8E0;">{html.escape(sc.grade_label)}</div>'
            f'<div style="font-size:11px;color:#7A7D96;margin-top:6px;">Est. default prob: <b style="color:{color};">{html.escape(sc.pd_band)}</b></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with g2:
        pct = sc.composite_score
        st.markdown(
            f'<div style="padding:6px 0;"><div style="font-size:12px;color:#7A7D96;">Composite score '
            f'<b style="color:{color};font-size:16px;">{pct:.0f}</b> / 100 '
            f'<span style="color:#555;">· industry profile: {html.escape(sc.industry_profile)}</span></div>'
            f'<div style="height:14px;background:#1E2030;border-radius:7px;overflow:hidden;margin:6px 0 14px 0;">'
            f'<div style="height:100%;width:{pct:.0f}%;background:{color};"></div></div></div>',
            unsafe_allow_html=True,
        )
        # Bucket bars
        for b, bscore in sc.buckets.items():
            if bscore is None:
                continue
            bcol = "#00FF88" if bscore >= 70 else "#FFB000" if bscore >= 45 else "#FF3333"
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;margin:3px 0;">'
                f'<span style="width:130px;font-size:11px;color:#9A9AB0;">{html.escape(b)}</span>'
                f'<div style="flex:1;height:8px;background:#1E2030;border-radius:4px;overflow:hidden;">'
                f'<div style="height:100%;width:{bscore:.0f}%;background:{bcol};"></div></div>'
                f'<span style="width:34px;text-align:right;font-size:11px;color:{bcol};">{bscore:.0f}</span></div>',
                unsafe_allow_html=True,
            )

    # ── Factor breakdown ──────────────────────────────────────────────────
    with st.expander("How this grade was built (factor breakdown)", expanded=True):
        rows = []
        for f in sc.factors:
            rows.append({
                "Bucket": f.bucket,
                "Factor": f.name,
                "Value": f.note,
                "Score": f"{f.score:.0f}" if f.score is not None else "—",
                "Weight": f"{f.weight:.0f}%",
                "Status": f.status,
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption(
            f"Data coverage: {sc.covered_weight*100:.0f}% of scorecard weight had values. "
            "Score = each factor graded 0–100 against its industry band; grade = weighted blend."
        )

    for n in sc.notes:
        st.markdown(
            f'<div style="font-size:11px;color:#9A9AB0;margin:4px 0;padding:6px 10px;background:#0B0C10;border-left:3px solid #333;border-radius:2px;">ℹ️ {html.escape(n)}</div>',
            unsafe_allow_html=True,
        )


def _render_anomalies_v3(workflow_state: dict[str, Any]) -> None:
    """Deterministic data & risk alerts (large swings, sign flips, identity breaks)."""
    rec = workflow_state.get("company_record")
    if not rec:
        return
    try:
        record = NormalizedCompanyRecord(**rec)
    except Exception:
        return

    report = detect_anomalies(record)
    if not report.anomalies:
        st.markdown(
            '<div style="font-size:12px;color:#00FF88;padding:8px 12px;background:#001A0D;'
            'border-left:3px solid #00FF88;border-radius:3px;">✓ No anomalies detected — the figures are internally consistent.</div>',
            unsafe_allow_html=True,
        )
        render_hr()
        return

    render_section_header("Data & Risk Alerts",
                          subtitle=f"{report.critical_count} critical · {report.warning_count} warning · auto-detected")
    sev_colors = {"critical": "#FF3333", "warning": "#FFB000", "info": "#00BFFF"}
    sev_icons = {"critical": "⛔", "warning": "⚠️", "info": "ℹ️"}
    for a in report.anomalies:
        c = sev_colors.get(a.severity, "#888")
        st.markdown(
            f'<div style="display:flex;gap:10px;align-items:flex-start;padding:6px 0;border-bottom:1px solid #1E2030;">'
            f'<span style="font-size:13px;">{sev_icons.get(a.severity, "•")}</span>'
            f'<span style="font-size:12px;color:#D8D8E0;line-height:1.5;">{html.escape(a.detail)} '
            f'<span style="color:{c};font-size:10px;font-weight:700;text-transform:uppercase;">[{html.escape(a.severity)}]</span></span></div>',
            unsafe_allow_html=True,
        )
    st.caption("These are flags for review, not verdicts. Ask the AI Assistant below to explain any of them.")
    render_hr()


def _render_trends_forecast_v3(workflow_state: dict[str, Any]) -> None:
    """V3 trend charts (revenue, margin history) + forward revenue forecast with scenarios."""
    record_data = workflow_state.get("company_record")
    if not record_data:
        return
    try:
        record = NormalizedCompanyRecord(**record_data)
    except Exception:
        return

    rev_series = sorted(record.revenue, key=lambda x: x.period)
    if len(rev_series) < 2:
        return  # nothing meaningful to trend

    render_section_header("Trends & Forecast", subtitle="V3 · history + forward projection with scenarios")
    ccy = record.currency

    c_left, c_right = st.columns(2)

    # ── Revenue history + forecast ────────────────────────────────────────
    with c_left:
        st.markdown("**Revenue — history & 3-year forecast**")
        fc = forecast_field(record, "revenue", years=3)
        data = {}
        hist_periods = [p for p, _ in [(x.period, x.value) for x in rev_series]]
        for x in rev_series:
            data.setdefault(x.period, {})["History"] = x.value
        if fc:
            # connect forecast lines to the last actual point
            last_p, last_v = fc.historical[-1]
            for label in ("Base", "Optimistic", "Pessimistic"):
                data.setdefault(last_p, {})[label] = last_v
            for pt in fc.points:
                data[pt.period] = {"Base": pt.base, "Optimistic": pt.optimistic, "Pessimistic": pt.pessimistic}
        df = pd.DataFrame(data).T.sort_index()
        st.line_chart(df, height=240)
        if fc and fc.cagr_pct is not None:
            st.caption(
                f"Historical CAGR **{fc.cagr_pct:.1f}%/yr**. Base grows at that rate; "
                f"optimistic **{fc.optimistic_growth_pct:.1f}%**, pessimistic **{fc.pessimistic_growth_pct:.1f}%**. "
                f"Latest actual: {format_money(fc.historical[-1][1], ccy)}."
            )

    # ── Margin trend ──────────────────────────────────────────────────────
    with c_right:
        st.markdown("**Operating margin trend**")
        op = {p.period: p.value for p in record.operating_income}
        rev = {p.period: p.value for p in record.revenue}
        margins = {}
        for period in sorted(rev):
            if period in op and abs(rev[period]) > 1e-9:
                margins[period] = round(op[period] / rev[period] * 100.0, 2)
        if len(margins) >= 2:
            st.line_chart(pd.DataFrame({"Operating margin %": margins}), height=240)
            latest = margins[sorted(margins)[-1]]
            first = margins[sorted(margins)[0]]
            trend = "improving" if latest > first else "declining" if latest < first else "flat"
            st.caption(f"Margin is **{trend}** — {first:.1f}% → {latest:.1f}% across the period.")
        else:
            st.caption("Not enough aligned revenue + operating income periods to chart margin.")

    render_hr()


def _scorecard_extra_lines(workflow_state: dict[str, Any]) -> list[str]:
    """Grade line to enrich the AI fact context (computed, not invented)."""
    rec = workflow_state.get("company_record")
    if not rec:
        return []
    try:
        record = NormalizedCompanyRecord(**rec)
    except Exception:
        return []
    profile = workflow_state.get("company_profile", {})
    sc = compute_scorecard(record, industry=record.industry or profile.get("industry"),
                           min_dscr=st.session_state.get("v3_min_dscr"))
    if sc.composite_score is None:
        return []
    return [f"Credit grade: {sc.grade} ({sc.grade_label}, composite {sc.composite_score:.0f}/100, PD {sc.pd_band})"]


def _render_ai_assistant_v3(workflow_state: dict[str, Any]) -> None:
    """Guardrailed AI: explains the computed facts and answers scoped questions."""
    if not workflow_state.get("company_record"):
        return
    render_hr()
    render_section_header("AI Assistant", subtitle="V3 · explains the computed facts — never invents numbers")

    extra = _scorecard_extra_lines(workflow_state)

    if st.button("🧠 Explain these results in plain English", use_container_width=False):
        with st.spinner("Reading the computed facts…"):
            st.session_state["ai_explain"] = explain_results(workflow_state, extra)

    if st.session_state.get("ai_explain"):
        st.markdown(
            f'<div style="font-size:13px;color:#D8D8E0;line-height:1.7;padding:14px;background:#0B0C10;'
            f'border:1px solid #1E2030;border-left:3px solid #00BFFF;border-radius:4px;">'
            f'{html.escape(st.session_state["ai_explain"])}</div>',
            unsafe_allow_html=True,
        )

    with st.form("ai_qa_form", clear_on_submit=True):
        q = st.text_input("Ask about this company",
                          placeholder="e.g. Is leverage a concern? What's driving the risk level? How strong is cash flow?",
                          label_visibility="collapsed")
        asked = st.form_submit_button("Ask")
    if asked and q.strip():
        with st.spinner("Thinking…"):
            ans = answer_question(q, workflow_state, extra)
        st.session_state.setdefault("ai_qa_history", []).append((q.strip(), ans))

    history = st.session_state.get("ai_qa_history", [])
    for qq, aa in reversed(history[-5:]):
        st.markdown(f'<div style="font-size:12px;color:#00BFFF;margin-top:10px;"><b>Q:</b> {html.escape(qq)}</div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:13px;color:#D8D8E0;line-height:1.6;padding:8px 12px;background:#0B0C10;border-radius:4px;"><b>A:</b> {html.escape(aa)}</div>',
                    unsafe_allow_html=True)

    st.caption("Answers use only the computed facts on this page. The AI cannot change any number, "
               "and will say so if something isn't in the data. Requires your local LLM endpoint to be running.")


def _render_credit_memo_v3(workflow_state: dict[str, Any]) -> None:
    """V3 one-page Credit Memo with printable/exportable HTML download."""
    record_data = workflow_state.get("company_record")
    if not record_data:
        return
    try:
        record = NormalizedCompanyRecord(**record_data)
    except Exception:
        return

    render_hr()
    render_section_header("Credit Memo", subtitle="V3 · one-page summary — download & print to PDF")

    profile = workflow_state.get("company_profile", {})
    industry = record.industry or profile.get("industry")
    min_dscr = st.session_state.get("v3_min_dscr")
    sc = compute_scorecard(record, industry=industry, min_dscr=min_dscr)

    credit_report = workflow_state.get("credit_report") or {}
    dscr_result = workflow_state.get("dscr_result") or {}
    dscr_risk = dscr_result.get("risk_level") if dscr_result else None

    memo = build_memo(
        record, sc,
        min_dscr=min_dscr,
        dscr_risk=dscr_risk,
        strengths=credit_report.get("major_strengths", []),
        risks=credit_report.get("major_risks", []),
        recommendation=credit_report.get("recommendation_narrative", ""),
    )
    memo_html = render_memo_html(memo)

    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.markdown(
            f'<div style="font-size:13px;color:#D8D8E0;">Grade <b style="color:#00BFFF;">{html.escape(memo.grade)}</b> '
            f'({html.escape(memo.grade_label)}) · PD {html.escape(memo.pd_band)}'
            + (f' · Min DSCR {memo.dscr_summary["min_dscr"]:.2f}x' if memo.dscr_summary else "")
            + '</div>',
            unsafe_allow_html=True,
        )
        st.caption("A clean lender-style memo assembling grade, highlights, strengths/risks and the assessment.")
    with col_b:
        safe_name = "".join(c if c.isalnum() else "_" for c in memo.entity_id)[:40]
        st.download_button(
            "⬇ Download Credit Memo (HTML → print to PDF)",
            data=memo_html,
            file_name=f"credit_memo_{safe_name}.html",
            mime="text/html",
            use_container_width=True,
        )

    with st.expander("Preview memo contents"):
        for h in memo.highlights:
            st.markdown(f"- **{h['label']}**: {h['value']}")


def page_analysis() -> None:
    render_section_header("Financial Analysis Output", subtitle="V2 Deterministic Metrics & Credit Assessment")

    outputs = st.session_state.get("agent_outputs")
    if not outputs:
        if not st.session_state.get("ocr_cache"):
            st.warning("⚠️ Please ingest data first by using the **Upload Statement** page.")
        else:
            st.warning("⚠️ Data loaded, but no financial analysis done yet. Please click **RUN FULL ANALYSIS** on the Upload page.")
        return

    entity = outputs.get("entity", "—")
    st.markdown(f'<div style="font-size:13px;color:#7A7D96;margin-bottom:24px;text-transform:uppercase;letter-spacing:0.08em;border-bottom:1px solid #1E2030;padding-bottom:12px;">Entity: <strong style="color:#FFB000;font-size:14px;">{html.escape(entity.upper())}</strong></div>', unsafe_allow_html=True)

    workflow_state = outputs.get("workflow_state", {})

    # ── V3: Verdict banner (one-line summary) ─────────────────────────────
    _render_verdict_banner_v3(workflow_state)

    # ── V3: Credit Scorecard headline (grade + PD) ────────────────────────
    _render_credit_scorecard_v3(workflow_state)
    render_hr()

    # ── V3: Data & Risk Alerts ────────────────────────────────────────────
    _render_anomalies_v3(workflow_state)

    # ── V3: Trends & Forecast ─────────────────────────────────────────────
    _render_trends_forecast_v3(workflow_state)

    # DSCR is now computed inline in the V3 "Debt Serviceability Analysis" section
    # below (no more go-back-and-re-run round-trip).
    dscr_result_data = workflow_state.get("dscr_result")

    # ── Layout: Two columns ───────────────────────────────────────────────
    c1, c2 = st.columns(2)

    with c1:
        # ── Revenue & SaaS Metrics ────────────────────────────────────────
        render_section_header("Revenue & SaaS Intelligence", subtitle="V2 Fact Ledger")

        # V2: Render SaaS metrics from fact ledger
        fact_ledger_data = workflow_state.get("fact_ledger")
        if fact_ledger_data:
            saas_entries = [e for e in fact_ledger_data.get("entries", []) if e.get("category") == "saas"]
            if saas_entries:
                saas_html = '<div class="bb-agent-card"><div class="bb-agent-card-title">SaaS Metrics (Actual Data)</div>'
                for entry in saas_entries:
                    val = entry.get("value")
                    name = entry.get("display_name", entry.get("metric", ""))
                    unit = entry.get("unit", "")
                    status = entry.get("status", "")
                    risk = entry.get("risk_signal")
                    risk_detail = entry.get("risk_detail", "")

                    val_color = "#E6E6E6"
                    if risk == "PASS": val_color = "#00FF88"
                    elif risk == "WARN": val_color = "#FFB000"
                    elif risk == "FAIL": val_color = "#FF3333"

                    if val is not None:
                        display_val = f"{val:.2f}{unit}" if unit == "%" else f"{val:.2f} {unit}"
                    elif status == "INSUFFICIENT_DATA":
                        display_val = "Insufficient Data"
                        val_color = "#666"
                    else:
                        display_val = "N/A"
                        val_color = "#666"

                    saas_html += f'''
                    <div class="bb-metric-row">
                        <span class="bb-mkey">{html.escape(name)}</span>
                        <span class="bb-mval" style="color:{val_color};">{html.escape(str(display_val))}</span>
                    </div>'''
                    _m = meaning_for(entry.get("metric"))
                    if _m:
                        saas_html += f'<div style="font-size:10px;color:#7A7D96;margin:-6px 0 6px 0;">{html.escape(_m)}</div>'
                    if risk_detail:
                        saas_html += f'<div style="font-size:10px;color:#7A7D96;margin:-4px 0 6px 0;padding-left:12px;">{html.escape(risk_detail)}</div>'

                saas_html += '</div>'
                st.markdown(saas_html, unsafe_allow_html=True)
                
                with st.expander("SaaS Metrics Methodology"):
                    st.markdown("**Formulas & Logic:**")
                    for entry in saas_entries:
                        st.markdown(f"- **{entry.get('display_name')}**: {entry.get('formula')}")

        # ── V2 Profitability Metrics ───────────────────────────
        if fact_ledger_data:
            profit_entries = [e for e in fact_ledger_data.get("entries", []) if e.get("category") == "profitability"]
            if profit_entries:
                cat_html = f'<div class="bb-agent-card" style="margin-top:12px;"><div class="bb-agent-card-title">Profitability Metrics</div>'
                for entry in profit_entries:
                    val = entry.get("value")
                    name = entry.get("display_name", "")
                    unit = entry.get("unit", "")
                    risk = entry.get("risk_signal")
                    val_color = "#E6E6E6"
                    if risk == "PASS": val_color = "#00FF88"
                    elif risk == "WARN": val_color = "#FFB000"
                    elif risk == "FAIL": val_color = "#FF3333"

                    if val is not None:
                        display_val = f"{val:.2f}{unit}" if unit in ("%",) else f"{val:,.2f} {unit}"
                    else:
                        display_val = "N/A"
                        val_color = "#666"

                    cat_html += f'''<div class="bb-metric-row">
                        <span class="bb-mkey">{html.escape(name)}</span>
                        <span class="bb-mval" style="color:{val_color};">{html.escape(display_val)}</span>
                    </div>'''
                    _m = meaning_for(entry.get("metric"))
                    if _m:
                        cat_html += f'<div style="font-size:10px;color:#7A7D96;margin:-6px 0 8px 0;">{html.escape(_m)}</div>'
                cat_html += '</div>'
                st.markdown(cat_html, unsafe_allow_html=True)
                
                with st.expander("Profitability Methodology Details"):
                    st.markdown("**Formulas & Logic:**")
                    for entry in profit_entries:
                        st.markdown(f"- **{entry.get('display_name')}**: {entry.get('formula')}")

        # ── V2 Peer Comparison (actual data, not hallucinated) ────────────
        peer_data = workflow_state.get("peer_comparison")
        if peer_data and peer_data.get("peers"):
            peers = peer_data["peers"]
            render_section_header("Peer Benchmarking", subtitle="Data from yfinance (actual, not estimated)")

            peers_html = f'''<div class="bb-agent-card" style="padding: 0; overflow-x: auto;">
<div style="padding:8px 12px;font-size:10px;color:#00FF88;background:#001A0D;border-bottom:1px solid #1E2030;">
✓ All peer data fetched from live sources — no LLM-estimated values
</div>
<table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px;">
<thead>
<tr style="border-bottom: 1px solid #1E2030; background: #0B0C10;">
<th style="padding: 10px; color: #7A7D96;">Company</th>
<th style="padding: 10px; color: #7A7D96;">Growth</th>
<th style="padding: 10px; color: #7A7D96;">Op. Margin</th>
<th style="padding: 10px; color: #7A7D96;">Gross Margin</th>
<th style="padding: 10px; color: #7A7D96;">D/E</th>
</tr>
</thead>
<tbody>'''
            for p in peers:
                name = p.get("entity_id", "Unknown")
                ticker = p.get("ticker", "")
                tier_badge = '<span style="font-size:9px;background:#003040;color:#00BFFF;padding:1px 4px;border-radius:2px;">PRIMARY</span>' if p.get("peer_tier") == "primary" else '<span style="font-size:9px;background:#1E2030;color:#7A7D96;padding:1px 4px;border-radius:2px;">SECONDARY</span>'

                def _fmt(v, suffix="%"):
                    return f"{v:.1f}{suffix}" if v is not None else "N/A"

                peers_html += f'''<tr style="border-bottom: 1px solid #1E2030;">
<td style="padding: 10px;">
<div style="color: #00BFFF; font-weight: bold;">{html.escape(name)} <span style="font-size:10px;color:#7A7D96;">{html.escape(ticker)}</span></div>
<div style="margin-top:2px;">{tier_badge}</div>
</td>
<td style="padding: 10px; color: #E6E6E6;">{_fmt(p.get("revenue_growth"))}</td>
<td style="padding: 10px; color: #E6E6E6;">{_fmt(p.get("operating_margin"))}</td>
<td style="padding: 10px; color: #E6E6E6;">{_fmt(p.get("gross_margin"))}</td>
<td style="padding: 10px; color: #E6E6E6;">{_fmt(p.get("debt_to_equity"), "x")}</td>
</tr>'''
            peers_html += "</tbody></table></div>"
            st.markdown(peers_html, unsafe_allow_html=True)

    with c2:
        render_section_header("Risk Dashboard", subtitle="Deterministic risk indicators")
        st.caption("Full DSCR (schedule + stress testing) is in the Debt Serviceability section below.")

        # ── Risk Dashboard ────────────────────────────────────────────────
        risk_data = workflow_state.get("risk_dashboard")
        if risk_data:
            overall = risk_data.get("overall_risk", "MODERATE")
            fail_ct = risk_data.get("fail_count", 0)
            warn_ct = risk_data.get("warn_count", 0)
            indicators = risk_data.get("indicators", [])

            risk_colors = {"LOW": "#00FF88", "MODERATE": "#FFB000", "HIGH": "#FF6B35", "CRITICAL": "#FF3333"}
            overall_color = risk_colors.get(overall, "#888")

            risk_html = f'''
            <div class="bb-agent-card" style="border-left: 4px solid {overall_color}; margin-top:16px;">
                <div class="bb-agent-card-title" style="color:{overall_color};">Risk Dashboard — Overall: {overall}</div>
                <div class="bb-metric-row">
                    <span class="bb-mkey" style="color:#FF3333;">FAIL Indicators</span>
                    <span class="bb-mval" style="color:#FF3333;">{fail_ct}</span>
                </div>
                <div class="bb-metric-row">
                    <span class="bb-mkey" style="color:#FFB000;">WARN Indicators</span>
                    <span class="bb-mval" style="color:#FFB000;">{warn_ct}</span>
                </div>
            </div>'''
            st.markdown(risk_html, unsafe_allow_html=True)

            # Show individual indicators
            if indicators:
                with st.expander(f"View All Risk Indicators ({len(indicators)})"):
                    for ind in indicators:
                        status = ind.get("status", "SKIP")
                        status_colors = {"PASS": "#00FF88", "WARN": "#FFB000", "FAIL": "#FF3333", "SKIP": "#888"}
                        sc = status_colors.get(status, "#888")
                        st.markdown(
                            f'<div style="display:flex;gap:10px;align-items:flex-start;padding:6px 0;border-bottom:1px solid #1E2030;">'
                            f'<span style="font-size:9px;font-weight:700;color:{sc};background:{sc}18;padding:1px 5px;border-radius:2px;letter-spacing:0.1em;white-space:nowrap;">{status}</span>'
                            f'<div>'
                            f'<span style="font-size:11px;color:#D8D8E0;font-weight:600;">{html.escape(ind.get("name", ""))}</span><br>'
                            f'<span style="font-size:10px;color:#7A7D96;">{html.escape(ind.get("detail", ""))}</span>'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )
                        
        # ── V2 Liquidity Metrics (fact ledger) ────────────
        _render_ledger_category(fact_ledger_data, "liquidity", "Liquidity")

        # ── V3 Working-Capital Cycle ──────────────────────
        _render_ledger_category(fact_ledger_data, "working_capital", "Working Capital Cycle")

        # ── V2 Solvency Metrics ───────────────────────────
        if fact_ledger_data:
            solv_entries = [e for e in fact_ledger_data.get("entries", []) if e.get("category") == "solvency"]
            if solv_entries:
                cat_html = f'<div class="bb-agent-card" style="margin-top:12px;"><div class="bb-agent-card-title">Solvency & Leverage</div>'
                for entry in solv_entries:
                    val = entry.get("value")
                    name = entry.get("display_name", "")
                    unit = entry.get("unit", "")
                    risk = entry.get("risk_signal")
                    val_color = "#E6E6E6"
                    if risk == "PASS": val_color = "#00FF88"
                    elif risk == "WARN": val_color = "#FFB000"
                    elif risk == "FAIL": val_color = "#FF3333"

                    if val is not None:
                        display_val = f"{val:.2f}{unit}" if unit in ("%",) else f"{val:,.2f} {unit}"
                    else:
                        display_val = "N/A"
                        val_color = "#666"

                    cat_html += f'''<div class="bb-metric-row">
                        <span class="bb-mkey">{html.escape(name)}</span>
                        <span class="bb-mval" style="color:{val_color};">{html.escape(display_val)}</span>
                    </div>'''
                    _m = meaning_for(entry.get("metric"))
                    if _m:
                        cat_html += f'<div style="font-size:10px;color:#7A7D96;margin:-6px 0 8px 0;">{html.escape(_m)}</div>'
                cat_html += '</div>'
                st.markdown(cat_html, unsafe_allow_html=True)
                
                with st.expander("Solvency Methodology Details"):
                    st.markdown("**Formulas & Logic:**")
                    for entry in solv_entries:
                        st.markdown(f"- **{entry.get('display_name')}**: {entry.get('formula')}")


    # ── V3: Debt Serviceability Analysis (interactive DSCR schedule + stress) ──
    _render_debt_serviceability_v3(workflow_state)

    # ── Credit Assessment Report ──────────────────────────────────────────
    render_hr()
    credit_report = workflow_state.get("credit_report")
    if credit_report:
        render_section_header("Credit Assessment Report", subtitle="V2 Synthesized by Credit Assessment Agent")

        # Strengths & Risks
        col_s, col_r = st.columns(2)
        with col_s:
            strengths = credit_report.get("major_strengths", [])
            if strengths:
                st.markdown("#### 💪 Major Strengths")
                for s in strengths:
                    st.markdown(f'<div style="font-size:12px;color:#00FF88;margin:4px 0;padding:6px 10px;background:#001A0D;border-left:3px solid #00FF88;border-radius:2px;">{html.escape(str(s))}</div>', unsafe_allow_html=True)

        with col_r:
            risks = credit_report.get("major_risks", [])
            if risks:
                st.markdown("#### ⚠️ Major Risks")
                for r in risks:
                    st.markdown(f'<div style="font-size:12px;color:#FF6B35;margin:4px 0;padding:6px 10px;background:#1A0D00;border-left:3px solid #FF6B35;border-radius:2px;">{html.escape(str(r))}</div>', unsafe_allow_html=True)

        # Recommendation narrative
        narrative = credit_report.get("recommendation_narrative", "")
        if narrative:
            st.markdown("#### 📋 Assessment Narrative")
            st.markdown(f'<div style="font-size:13px;color:#D8D8E0;line-height:1.7;padding:16px;background:#0B0C10;border:1px solid #1E2030;border-radius:4px;">{html.escape(narrative)}</div>', unsafe_allow_html=True)

        # Disclaimer
        disclaimer = credit_report.get("disclaimer", "")
        if disclaimer:
            st.markdown(f'<div style="font-size:10px;color:#7A7D96;margin-top:12px;padding:8px;background:#070809;border:1px solid #1E2030;border-radius:2px;font-style:italic;">{html.escape(disclaimer)}</div>', unsafe_allow_html=True)

    # ── Qualitative Findings ──────────────────────────────────────────────
    qual_findings = workflow_state.get("qualitative_findings", [])
    if qual_findings and any(f != "No qualitative corporate intelligence available for this company." for f in qual_findings):
        render_hr()
        render_section_header("Qualitative Corporate Intelligence", subtitle="Extracted from management commentary")
        for f in qual_findings:
            st.markdown(f'<div style="font-size:12px;color:#CC88FF;margin:4px 0;padding:6px 10px;background:#0D0020;border-left:3px solid #CC88FF;border-radius:2px;">{html.escape(str(f))}</div>', unsafe_allow_html=True)

    # ── V3: Credit Memo (printable / exportable) ──────────────────────────
    _render_ai_assistant_v3(workflow_state)

    _render_credit_memo_v3(workflow_state)

    # ── Workflow Log ──────────────────────────────────────────────────────
    workflow_log = workflow_state.get("workflow_log", [])
    if workflow_log:
        render_hr()
        with st.expander("Agent Workflow Log (Transparency)"):
            for log_entry in workflow_log:
                st.markdown(f'<span style="font-size:10px;color:#7A7D96;font-family:monospace;">{html.escape(str(log_entry))}</span>', unsafe_allow_html=True)

    # ── Developer / Audit data (hidden by default) ────────────────────────
    render_hr()
    show_dev = st.checkbox("🔧 Show developer / audit data (raw JSON)", value=False,
                           help="The full computed data behind every number — for auditing, not everyday use.")
    if show_dev:
        render_section_header("Raw Workflow Output", subtitle="Full JSON — audit trail")
        with st.expander("Workflow State (fact ledger, DSCR, peers, report)"):
            st.json(outputs.get("workflow_state", {}))


# ── Page 4 ────────────────────────────────────────────────────────────────────

def page_basel() -> None:
    render_section_header("Basel III Risk Governance Alignment", subtitle="How this system supports regulatory frameworks")

    st.markdown("""
        <div class="bb-basel-panel">
            <div class="bb-section-title" style="margin-bottom:12px;">System Overview</div>
            <p class="bb-body-text">This Explainable Financial Analysis System supports Basel III-aligned risk governance
            workflows. It provides transparent, auditable, and explainable financial risk indicators derived from
            structured Bloomberg financial statements. All numeric computations are performed deterministically in Python —
            the LLM is used exclusively for natural-language explanation of pre-computed metrics, ensuring full auditability.</p>
        </div>

        <div class="bb-basel-panel">
            <div class="bb-section-title" style="margin-bottom:12px;">Regulatory Pillar Alignment</div>
            <span class="bb-pillar-badge">Pillar 2</span>
            <p class="bb-body-text" style="margin-top:8px;">Supports <b>Pillar 2 supervisory monitoring</b> by providing
            structured, explainable outputs for internal credit risk review. Revenue trends, liquidity ratios, and
            balance sheet leverage metrics are presented with full transparency, enabling risk officers to trace every
            figure back to its source data.</p>
            <span class="bb-pillar-badge" style="border-color:#00BFFF;color:#00BFFF;background:#001A2E;">Pillar 3</span>
            <p class="bb-body-text" style="margin-top:8px;">Explainability of outputs aligns with <b>Pillar 3 market
            discipline</b> requirements. The cross-reference agent produces integrated narratives bridging quantitative
            metrics with qualitative risk language.</p>
        </div>

        <div class="bb-basel-panel">
            <div class="bb-section-title" style="margin-bottom:12px;">Scope &amp; Limitations</div>
            <p class="bb-body-text"><span style="color:#FF6B35;">⚠ Important:</span> This system does <b>not</b>
            calculate regulatory capital adequacy ratios, Tier 1/Tier 2 capital buffers, LCR, NSFR, or any other
            binding Basel III regulatory measure. It is not a substitute for regulatory reporting or prudential supervision.</p>
            <p class="bb-body-text">Intended use cases:</p>
            <ul style="font-size:12px;color:#CCCCCC;line-height:1.8;padding-left:20px;">
                <li>Structured financial statement review workflows</li>
                <li>Preliminary credit background checks based on public filings</li>
                <li>Risk trend monitoring across multiple reporting periods</li>
                <li>Generation of explainable, auditable financial summaries</li>
            </ul>
        </div>

        <div class="bb-basel-panel">
            <div class="bb-section-title" style="margin-bottom:14px;">Agent &#x2192; Framework Mapping</div>
            <div class="bb-metric-row">
                <span class="bb-mkey" style="color:#FFB000;">Revenue Agent</span>
                <span class="bb-mval" style="font-size:11px;">Income stability &#xB7; Earnings trend analysis</span>
            </div>
            <div class="bb-metric-row">
                <span class="bb-mkey" style="color:#00BFFF;">Liquidity Agent</span>
                <span class="bb-mval" style="font-size:11px;">Working capital adequacy &#xB7; LCR-adjacent indicators</span>
            </div>
            <div class="bb-metric-row">
                <span class="bb-mkey" style="color:#FF6B35;">Balance Sheet Agent</span>
                <span class="bb-mval" style="font-size:11px;">Leverage ratio monitoring &#xB7; Asset quality signals</span>
            </div>
            <div class="bb-metric-row">
                <span class="bb-mkey" style="color:#00FF88;">Cross Reference Agent</span>
                <span class="bb-mval" style="font-size:11px;">Integrated risk narrative &#xB7; Pillar 2 reporting aid</span>
            </div>
        </div>
    """, unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────

