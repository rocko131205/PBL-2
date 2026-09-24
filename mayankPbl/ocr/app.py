"""FinVeritas — entry point / router.

Flow: login (auth/) -> upload (ingestion/upload_page) -> analysis (analysis/analysis_page).
Page code lives in its feature package; this file wires auth, sidebar nav, and routing."""
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

from ingestion.upload_page import page_upload
from analysis.analysis_page import page_workflow, page_analysis, page_basel

_DEFAULT_BASE_URL     = os.getenv("LLM_BASE_URL") or os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
_DEFAULT_MODEL        = os.getenv("LLM_MODEL", "qwen2.5-coder-1.5b-instruct-mlx")
_DEFAULT_API_KEY      = os.getenv("LLM_API_KEY", "local")
_DEFAULT_NEWS_API_KEY = os.getenv("NEWSAPI_KEY", "")
_DEFAULT_FMP_KEY      = os.getenv("FMP_API_KEY", "")
_DEFAULT_AV_KEY       = ""


def main() -> None:
    st.set_page_config(
        page_title="FinVeritas — Financial Analysis Platform",
        page_icon="⬡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    load_css()

    import time

    if st.query_params.get("logout") == "1":
        st.session_state.clear()
        st.query_params.clear()
        st.toast("Successfully signed out.", icon="👋")

    # ── Auth gate ─────────────────────────────────────────────────────────────
    # On page load, check URL query params for a persisted JWT token.
    token = st.query_params.get("token") or st.session_state.get("auth_token")
    user: dict | None = None
    if token:
        user = decode_token(token)
        if user:
            # Inactivity timeout check (15 minutes)
            last_active = st.session_state.get("last_active_time", time.time())
            if time.time() - last_active > 15 * 60:
                st.query_params.clear()
                st.session_state.pop("auth_token", None)
                st.session_state.pop("auth_user", None)
                st.toast("Locked due to 15 minutes of inactivity.", icon="🔒")
                user = None
            else:
                st.session_state["last_active_time"] = time.time()
                st.session_state["auth_token"] = token
                st.session_state["auth_user"]  = user
                
        if not user:
            # Token expired or invalid — clear it and ask to log in again
            st.query_params.clear()
            st.session_state.pop("auth_token", None)
            st.session_state.pop("auth_user", None)

    if not user:
        # Show correct auth sub-page
        auth_page = st.session_state.get("auth_page", "login")
        if auth_page == "register":
            page_register()
        elif auth_page == "forgot":
            page_forgot_password()
        else:
            page_login()
        st.stop()  # Nothing else renders until authenticated

    # ── Theme / font prefs ────────────────────────────────────────────────────
    _light  = st.session_state.get("light_mode", False)
    _fscale = st.session_state.get("font_scale", 1.0)
    inject_theme_vars(font_scale=_fscale, light_mode=_light)

    # ── Entity name for top bar ───────────────────────────────────────────────
    entity = "—"
    cached = st.session_state.get("ocr_cache", {})
    if cached:
        _pl = cached.get("payload") or {}
        entity = str(_pl.get("entity", {}).get("entity_id") or "—")

    render_top_bar(entity=entity, user_name=user.get("full_name", ""))

    # ── Nav page (auto-redirect after analysis runs) ──────────────────────────
    _nav_target = st.session_state.pop("nav_page", None)

    with st.sidebar:
        st.markdown("""
            <div class="bb-sidebar-logo">
                <div class="bb-sidebar-brand-mark">FV</div>
                <div>
                    <div class="bb-sidebar-logo-text">FinVeritas</div>
                    <div class="bb-sidebar-logo-sub">Financial Analysis</div>
                </div>
            </div>""", unsafe_allow_html=True)

        st.markdown('<div class="bb-nav-label">Navigation</div>', unsafe_allow_html=True)

        _nav_options = [
            "Upload Statement",
            "Financial Analysis",
            "Agent Workflow",
            "Basel III Alignment",
            "My File History",
        ]
        # Default index — use nav_target if set (auto-redirect)
        _default_idx = 0
        if _nav_target and _nav_target in _nav_options:
            _default_idx = _nav_options.index(_nav_target)

        page = st.radio("",
            _nav_options,
            index=_default_idx,
            label_visibility="collapsed",
            key="sidebar_nav",
        )

        render_hr()
        st.markdown('<div class="bb-nav-label" style="margin-top:8px;">Display</div>', unsafe_allow_html=True)
        theme_choice = st.radio("",
            ["Dark", "Light"],
            index=1 if _light else 0,
            horizontal=True,
            label_visibility="collapsed",
            key="theme_radio",
        )
        new_light = (theme_choice == "Light")
        if new_light != _light:
            st.session_state["light_mode"] = new_light
            st.rerun()
        font_scale = st.slider(
            "Font size", min_value=0.8, max_value=1.4, value=_fscale, step=0.1,
            format="%.1fx", key="font_scale_slider",
        )
        if font_scale != _fscale:
            st.session_state["font_scale"] = font_scale
            st.rerun()

        # Secrets are securely loaded from .env behind the scenes
        base_url     = _DEFAULT_BASE_URL
        model        = _DEFAULT_MODEL
        api_key      = _DEFAULT_API_KEY
        news_api_key = _DEFAULT_NEWS_API_KEY
        fmp_api_key  = _DEFAULT_FMP_KEY
        av_api_key   = ""

        render_hr()
        has_data    = bool(st.session_state.get("ocr_cache"))
        has_results = bool(st.session_state.get("agent_outputs"))
        st.markdown(
            f'<div style="font-size:9px;color:#444;line-height:2;letter-spacing:0.05em;">'
            f'OCR DATA&nbsp;&nbsp; <span style="color:{"#00FF88" if has_data else "#333"};">{"■ LOADED" if has_data else "□ NONE"}</span><br>'
            f'ANALYSIS&nbsp;&nbsp; <span style="color:{"#00FF88" if has_results else "#333"};">{"■ READY" if has_results else "□ NONE"}</span>'
            f"</div>", unsafe_allow_html=True)

    # ── Route to page ─────────────────────────────────────────────────────────
    if "Upload" in page:
        page_upload(base_url, model, api_key, news_api_key,
                    fmp_api_key=fmp_api_key, av_api_key=av_api_key)
    elif "Workflow" in page:
        page_workflow()
    elif "Analysis" in page:
        page_analysis()
    elif "Basel" in page:
        page_basel()
    elif "History" in page:
        page_history(user_id=user["user_id"])


if __name__ == "__main__":
    main()

