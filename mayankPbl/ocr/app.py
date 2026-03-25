"""Bloomberg Terminal-style Explainable Financial Analysis System.

Pages
-----
1. Upload Financial Statement  — multi-PDF upload, OCR, metric cards, run agents
2. Agent Workflow              — interactive pipeline diagram with hover tooltips
3. Financial Analysis          — full agent output cards
4. Basel III Alignment         — regulatory context panel
"""
from __future__ import annotations

import traceback
from typing import Any

import pandas as pd
import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from agents import (
    balance_sheet_agent,
    cross_reference_agent,
    liquidity_agent,
    revenue_agent,
    sentiment_agent,
)
from ocr.pdf_parser import parse_pdf_to_json
from ui.dashboard_components import (
    agent_tooltip_html,
    load_css,
    render_agent_card,
    render_cross_ref_card,
    render_hr,
    render_metric_cards,
    render_section_header,
    render_top_bar,
)

_DEFAULT_BASE_URL    = "http://127.0.0.1:1234/v1"
_DEFAULT_MODEL       = "qwen2.5-coder-1.5b-instruct-mlx"
_DEFAULT_API_KEY     = "local"
_DEFAULT_NEWS_API_KEY = ""


def _safe_run(name: str, fn) -> dict[str, Any]:
    try:
        return fn()
    except Exception as exc:
        return {"error": f"{name} failed: {exc}", "traceback": traceback.format_exc()}


def _preview_df(payload: dict[str, Any]) -> pd.DataFrame:
    ts = payload.get("time_series") or {}
    fields = ["revenue", "total_assets", "total_liabilities", "equity"]
    rows = []
    for field in fields:
        for item in ts.get(field) or []:
            if isinstance(item, dict) and item.get("value") is not None:
                rows.append({"field": field, "period": item.get("period"), "value": item.get("value")})
    if not rows:
        return pd.DataFrame(columns=["field", "period", "value"])
    df = pd.DataFrame(rows).dropna(subset=["period", "value"])
    df["period"] = df["period"].astype(str)
    df = df.sort_values(["field", "period"]).groupby("field", as_index=False).tail(5)
    return df[["field", "period", "value"]]


def _available_fields(payload: dict[str, Any]) -> set[str]:
    ts = payload.get("time_series") or {}
    return {k for k, v in ts.items() if isinstance(v, list) and len(v) > 0}


# ── Page 1 ────────────────────────────────────────────────────────────────────

def page_upload(base_url: str, model: str, api_key: str, news_api_key: str = "") -> None:
    render_section_header(
        "Upload Bloomberg Financial Statement",
        subtitle="Upload Income Statement + Balance Sheet PDFs for full analysis",
    )
    st.markdown(
        '<p style="font-size:11px;color:#666;font-family:monospace;">'
        "▸ Upload <b>both</b> the Income Statement PDF and the Balance Sheet PDF together "
        "to enable all agents. A single IS PDF enables the Revenue Agent only.</p>",
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        "Drop Bloomberg PDF(s) here", type=["pdf"],
        accept_multiple_files=True, label_visibility="collapsed",
    )

    if not uploaded_files:
        st.markdown('<div style="color:#444;font-size:11px;margin-top:8px;">▸ Awaiting upload…</div>', unsafe_allow_html=True)
        return

    cache_key = tuple(sorted(f.name for f in uploaded_files))
    cached = st.session_state.get("ocr_cache", {})

    if cached.get("cache_key") != cache_key:
        uploads = [(f.getvalue(), f.name) for f in uploaded_files]
        with st.spinner(f"Running OCR parser on {len(uploads)} file(s)…"):
            try:
                payload, written_path, agent_paths = parse_pdf_to_json(uploads=uploads, output_dir="output")
            except Exception as exc:
                st.error(f"OCR failed: {exc}")
                return
        st.session_state["ocr_cache"] = {
            "cache_key": cache_key, "payload": payload,
            "written_path": written_path, "agent_paths": agent_paths,
        }
        st.session_state.pop("agent_outputs", None)
        st.success(f"OCR complete — {len(uploads)} PDF(s) merged → `{written_path.name}`")
    else:
        payload = cached["payload"]; written_path = cached["written_path"]; agent_paths = cached["agent_paths"]
        st.info(f"Cached OCR result: `{written_path.name}`")

    render_section_header("Extracted Key Metrics", subtitle=f"Source: {written_path.name}")
    render_metric_cards(payload)

    with st.expander("Raw Data Preview", expanded=False):
        st.dataframe(_preview_df(payload), use_container_width=True)

    render_hr()

    avail = _available_fields(payload)
    required_liq = {"current_assets", "current_liabilities", "total_assets", "total_liabilities", "equity"}
    required_bs  = {"total_assets", "total_liabilities", "equity"}
    missing_liq  = sorted(required_liq - avail)
    missing_bs   = sorted(required_bs  - avail)

    cols = st.columns(5)
    statuses = [
        ("REVENUE",       "revenue" in avail,                      "#FFB000"),
        ("LIQUIDITY",     not missing_liq,                          "#00BFFF"),
        ("BALANCE SHEET", not missing_bs,                           "#FF6B35"),
        ("SENTIMENT",     bool(news_api_key and news_api_key.strip()), "#CC88FF"),
        ("CROSS REF",     not missing_liq and not missing_bs,       "#00FF88"),
    ]
    for col, (name, ready, colour) in zip(cols, statuses):
        c = colour if ready else "#444"
        col.markdown(
            f'<div style="text-align:center;font-size:10px;color:{c};">{"●" if ready else "○"}&nbsp;{name}<br>'
            f'<span style="font-size:9px;color:#555;">{"READY" if ready else "MISSING DATA"}</span></div>',
            unsafe_allow_html=True,
        )

    render_hr()
    render_section_header("Run Agent Pipeline")

    if st.button("▶  RUN FULL ANALYSIS", use_container_width=False):
        rev_path = agent_paths["revenue"]
        bs_path  = agent_paths["balance_sheet"]
        liq_path = agent_paths["liquidity"]
        entity = str(payload.get("entity", {}).get("entity_id") or "UNKNOWN")

        with st.spinner("Revenue Agent…"):
            rev_out = _safe_run("Revenue Agent",
                lambda: revenue_agent.run(json_path=rev_path, base_url=base_url, model=model, api_key=api_key))

        liq_out = ({"error": f"Liquidity Agent skipped — missing: {', '.join(missing_liq)}"} if missing_liq else
            _safe_run("Liquidity Agent", lambda: liquidity_agent.run(json_path=liq_path, base_url=base_url, model=model, api_key=api_key)))
        if not missing_liq:
            with st.spinner("Liquidity Agent…"):
                liq_out = _safe_run("Liquidity Agent",
                    lambda: liquidity_agent.run(json_path=liq_path, base_url=base_url, model=model, api_key=api_key))

        bs_out = ({"error": f"Balance Sheet Agent skipped — missing: {', '.join(missing_bs)}"} if missing_bs else None)
        if not missing_bs:
            with st.spinner("Balance Sheet Agent…"):
                bs_out = _safe_run("Balance Sheet Agent",
                    lambda: balance_sheet_agent.run(json_path=bs_path, base_url=base_url, model=model, api_key=api_key))

        # Sentiment Agent — optional; skipped gracefully if no NewsAPI key provided
        _news_key = news_api_key.strip() if news_api_key else ""
        if not _news_key:
            sentiment_out: dict = {"error": "Sentiment Agent skipped — add a NewsAPI key in the sidebar (newsapi.org)."}
        else:
            with st.spinner("Sentiment Agent…"):
                _entity_for_sentiment = entity  # capture for lambda closure
                _key_for_sentiment = _news_key
                sentiment_out = _safe_run(
                    "Sentiment Agent",
                    lambda: sentiment_agent.run(
                        company_name=_entity_for_sentiment,
                        news_api_key=_key_for_sentiment,
                        base_url=base_url,
                        model=model,
                        api_key=api_key,
                    ),
                )

        # Pass sentiment to cross-reference only if it succeeded
        _sentiment_ok = sentiment_out and not isinstance(sentiment_out.get("error"), str)
        any_err = any(isinstance(x.get("error"), str) for x in [rev_out, liq_out, bs_out])
        if any_err:
            cross_out = {"error": "Cross Reference Agent skipped — requires Revenue, Liquidity, and Balance Sheet agents to succeed."}
        else:
            with st.spinner("Cross Reference Agent…"):
                cross_out = _safe_run(
                    "Cross Reference Agent",
                    lambda: cross_reference_agent.run(
                        entity=entity,
                        revenue=rev_out,
                        liquidity=liq_out,
                        balance_sheet=bs_out,
                        sentiment=sentiment_out if _sentiment_ok else None,
                        base_url=base_url,
                        model=model,
                        api_key=api_key,
                    ),
                )

        st.session_state["agent_outputs"] = {
            "entity": entity, "revenue": rev_out, "liquidity": liq_out,
            "balance_sheet": bs_out, "sentiment": sentiment_out, "cross_reference": cross_out,
        }
        st.success("Analysis complete — navigate to Financial Analysis to view results.")

    outputs = st.session_state.get("agent_outputs")
    if outputs:
        render_section_header("Agent Status Summary")
        for label, key, variant in [
            ("Revenue Agent", "revenue", ""),
            ("Liquidity Agent", "liquidity", "liq"),
            ("Balance Sheet Agent", "balance_sheet", "bs"),
            ("Sentiment Agent", "sentiment", ""),
            ("Cross Reference Agent", "cross_reference", "xref"),
        ]:
            render_agent_card(label, outputs.get(key, {}), css_variant=variant)


# ── Page 2 ────────────────────────────────────────────────────────────────────

def page_workflow() -> None:
    render_section_header("Agent Pipeline Architecture", subtitle="Hover over nodes to inspect outputs")

    outputs = st.session_state.get("agent_outputs") or {}

    st.markdown("""
        <div class="bb-workflow-legend">
            <div class="bb-legend-item"><span class="bb-legend-dot" style="background:#4A4A5A"></span>I/O Nodes</div>
            <div class="bb-legend-item"><span class="bb-legend-dot" style="background:#0D3B66"></span>OCR Parser</div>
            <div class="bb-legend-item"><span class="bb-legend-dot" style="background:#3B2800"></span>Revenue Agent</div>
            <div class="bb-legend-item"><span class="bb-legend-dot" style="background:#003040"></span>Liquidity Agent</div>
            <div class="bb-legend-item"><span class="bb-legend-dot" style="background:#3B1800"></span>Balance Sheet Agent</div>
            <div class="bb-legend-item"><span class="bb-legend-dot" style="background:#2A0040"></span>Sentiment Agent</div>
            <div class="bb-legend-item"><span class="bb-legend-dot" style="background:#002010"></span>Cross Reference</div>
        </div>""", unsafe_allow_html=True)

    nodes = [
        Node(id="pdf",   label="PDF\nInput",            color="#1A1A2E", shape="box",     size=20, font={"color":"#CCCCCC","size":12}, title="Bloomberg Financial Statement PDF(s)"),
        Node(id="news",  label="News\nAPI",              color="#1A1A2E", shape="box",     size=20, font={"color":"#CC88FF","size":12}, title="NewsAPI — latest company news headlines (newsapi.org)"),
        Node(id="ocr",   label="OCR\nParser",            color="#0D3B66", shape="box",     size=20, font={"color":"#00BFFF","size":12}, title="<b>OCR Parser</b><br>Extracts IS + BS data from PDFs<br>Writes 4 JSON files to output/"),
        Node(id="rev",   label="Revenue\nAgent",         color="#3B2800", shape="ellipse", size=22, font={"color":"#FFB000","size":12}, title=agent_tooltip_html("Revenue Agent",       outputs.get("revenue"))),
        Node(id="liq",   label="Liquidity\nAgent",       color="#003040", shape="ellipse", size=22, font={"color":"#00BFFF","size":12}, title=agent_tooltip_html("Liquidity Agent",     outputs.get("liquidity"))),
        Node(id="bs",    label="Balance Sheet\nAgent",   color="#3B1800", shape="ellipse", size=22, font={"color":"#FF6B35","size":12}, title=agent_tooltip_html("Balance Sheet Agent", outputs.get("balance_sheet"))),
        Node(id="sent",  label="Sentiment\nAgent",       color="#2A0040", shape="ellipse", size=22, font={"color":"#CC88FF","size":12}, title=agent_tooltip_html("Sentiment Agent",     outputs.get("sentiment"))),
        Node(id="cross", label="Cross\nReference\nAgent",color="#002010", shape="box",     size=24, font={"color":"#00FF88","size":12}, title=agent_tooltip_html("Cross Reference Agent",outputs.get("cross_reference"))),
        Node(id="out",   label="Explainable\nOutput",    color="#1A1A2E", shape="box",     size=20, font={"color":"#E6E6E6","size":12}, title="Final explainable financial analysis report"),
    ]
    edges = [
        Edge(source="pdf",   target="ocr",   color="#333344", width=2),
        Edge(source="news",  target="sent",  color="#CC88FF", width=2),
        Edge(source="ocr",   target="rev",   color="#FFB000", width=1),
        Edge(source="ocr",   target="liq",   color="#00BFFF", width=1),
        Edge(source="ocr",   target="bs",    color="#FF6B35", width=1),
        Edge(source="rev",   target="cross", color="#FFB000", width=1, dashes=True),
        Edge(source="liq",   target="cross", color="#00BFFF", width=1, dashes=True),
        Edge(source="bs",    target="cross", color="#FF6B35", width=1, dashes=True),
        Edge(source="sent",  target="cross", color="#CC88FF", width=1, dashes=True),
        Edge(source="cross", target="out",   color="#00FF88", width=2),
    ]
    config = Config(width="100%", height=520, directed=True, physics=False, hierarchical=True,
                    hierarchical_sort_method="directed", nodeHighlightBehavior=True, highlightColor="#FFB000", collapsible=False)
    agraph(nodes=nodes, edges=edges, config=config)

    render_hr()
    if outputs:
        render_section_header("Agent Output Detail", subtitle="Expanded metrics per agent")
        c1, c2 = st.columns(2)
        with c1:
            render_agent_card("Revenue Agent",       outputs.get("revenue", {}),       css_variant="")
            render_agent_card("Balance Sheet Agent", outputs.get("balance_sheet", {}), css_variant="bs")
            render_agent_card("Sentiment Agent",     outputs.get("sentiment", {}),     css_variant="")
        with c2:
            render_agent_card("Liquidity Agent",     outputs.get("liquidity", {}),     css_variant="liq")
            render_cross_ref_card(outputs.get("cross_reference", {}))
    else:
        st.markdown('<div style="color:#444;font-size:11px;margin-top:12px;">▸ Run analysis on the Upload page to populate node tooltips.</div>', unsafe_allow_html=True)


# ── Page 3 ────────────────────────────────────────────────────────────────────

def page_analysis() -> None:
    render_section_header("Financial Analysis Output", subtitle="Deterministic metrics + LLM explanations")

    outputs = st.session_state.get("agent_outputs")
    if not outputs:
        st.markdown('<div style="color:#444;font-size:12px;">▸ No analysis data yet. Upload PDFs and run the pipeline first.</div>', unsafe_allow_html=True)
        return

    entity = outputs.get("entity", "—")
    st.markdown(f'<div style="font-size:10px;color:#555;margin-bottom:16px;">ENTITY: <span style="color:#FFB000;">{entity.upper()}</span></div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        render_section_header("Revenue Agent", subtitle="Income Statement Analysis")
        render_agent_card("Revenue Agent", outputs.get("revenue", {}), css_variant="", icon="◆")
    with c2:
        render_section_header("Liquidity Agent", subtitle="Working Capital & Funding Stability")
        render_agent_card("Liquidity Agent", outputs.get("liquidity", {}), css_variant="liq", icon="◈")

    render_hr()

    c3, c4 = st.columns(2)
    with c3:
        render_section_header("Balance Sheet Agent", subtitle="Leverage & Asset Growth")
        render_agent_card("Balance Sheet Agent", outputs.get("balance_sheet", {}), css_variant="bs", icon="◇")
    with c4:
        render_section_header("Sentiment Agent", subtitle="Public Perception from Latest News")
        render_agent_card("Sentiment Agent", outputs.get("sentiment", {}), css_variant="", icon="◉")

    render_hr()
    render_section_header("Cross Reference Agent", subtitle="Integrated Explainable Summary — Financial + Sentiment")
    render_cross_ref_card(outputs.get("cross_reference", {}))

    render_hr()
    render_section_header("Raw Agent Outputs", subtitle="Full JSON — audit trail")
    for label, key in [
        ("Revenue Agent", "revenue"), ("Liquidity Agent", "liquidity"),
        ("Balance Sheet Agent", "balance_sheet"), ("Sentiment Agent", "sentiment"),
        ("Cross Reference Agent", "cross_reference"),
    ]:
        with st.expander(f"{label}"):
            st.json(outputs.get(key, {}))


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
            <div class="bb-section-title" style="margin-bottom:14px;">Agent → Framework Mapping</div>
            <div class="bb-metric-row">
                <span class="bb-mkey" style="color:#FFB000;">Revenue Agent</span>
                <span class="bb-mval" style="font-size:11px;">Income stability · Earnings trend analysis</span>
            </div>
            <div class="bb-metric-row">
                <span class="bb-mkey" style="color:#00BFFF;">Liquidity Agent</span>
                <span class="bb-mval" style="font-size:11px;">Working capital adequacy · LCR-adjacent indicators</span>
            </div>
            <div class="bb-metric-row">
                <span class="bb-mkey" style="color:#FF6B35;">Balance Sheet Agent</span>
                <span class="bb-mval" style="font-size:11px;">Leverage ratio monitoring · Asset quality signals</span>
            </div>
            <div class="bb-metric-row">
                <span class="bb-mkey" style="color:#00FF88;">Cross Reference Agent</span>
                <span class="bb-mval" style="font-size:11px;">Integrated risk narrative · Pillar 2 reporting aid</span>
            </div>
        </div>
    """, unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="Financial Analysis Terminal", page_icon="▪", layout="wide", initial_sidebar_state="expanded")
    load_css()

    entity = "—"
    cached = st.session_state.get("ocr_cache", {})
    if cached:
        payload = cached.get("payload") or {}
        entity = str(payload.get("entity", {}).get("entity_id") or "—")

    render_top_bar(entity=entity)

    with st.sidebar:
        st.markdown("""
            <div class="bb-sidebar-logo">
                <div class="bb-sidebar-logo-icon">▪</div>
                <div class="bb-sidebar-logo-text">Financial Terminal</div>
            </div>""", unsafe_allow_html=True)

        st.markdown('<div class="bb-nav-label">Navigation</div>', unsafe_allow_html=True)
        page = st.radio("",
            ["Upload Statement", "Agent Workflow", "Financial Analysis", "Basel III Alignment"],
            label_visibility="collapsed")

        render_hr()
        st.markdown('<div class="bb-nav-label" style="margin-top:8px;">⚙  LLM Settings</div>', unsafe_allow_html=True)
        base_url = st.text_input("Base URL", value=_DEFAULT_BASE_URL)
        model    = st.text_input("Model",    value=_DEFAULT_MODEL)
        api_key  = st.text_input("API Key",  value=_DEFAULT_API_KEY, type="password")

        render_hr()
        st.markdown('<div class="bb-nav-label" style="margin-top:8px;">📰  News Settings</div>', unsafe_allow_html=True)
        news_api_key = st.text_input(
            "NewsAPI Key", value=_DEFAULT_NEWS_API_KEY, type="password",
            help="Free key at newsapi.org — enables the Sentiment Agent",
        )

        render_hr()
        has_data    = bool(st.session_state.get("ocr_cache"))
        has_results = bool(st.session_state.get("agent_outputs"))
        st.markdown(
            f'<div style="font-size:9px;color:#444;line-height:2;letter-spacing:0.05em;">'
            f'OCR DATA&nbsp;&nbsp; <span style="color:{"#00FF88" if has_data else "#333"};">{"■ LOADED" if has_data else "□ NONE"}</span><br>'
            f'ANALYSIS&nbsp;&nbsp; <span style="color:{"#00FF88" if has_results else "#333"};">{"■ READY" if has_results else "□ NONE"}</span>'
            f"</div>", unsafe_allow_html=True)

    if "Upload" in page:
        page_upload(base_url, model, api_key, news_api_key)
    elif "Workflow" in page:
        page_workflow()
    elif "Analysis" in page:
        page_analysis()
    elif "Basel" in page:
        page_basel()


if __name__ == "__main__":
    main()
