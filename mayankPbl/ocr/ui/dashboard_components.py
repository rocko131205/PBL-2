"""Bloomberg Terminal-style reusable UI components.

All HTML is injected via st.markdown(..., unsafe_allow_html=True).
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
# CSS loader
# ─────────────────────────────────────────────────────────────────────────────

def load_css() -> None:
    """Inject the Bloomberg Terminal CSS into the Streamlit app."""
    css_path = Path(__file__).parent / "styles.css"
    if css_path.exists():
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Top bar
# ─────────────────────────────────────────────────────────────────────────────

def render_top_bar(entity: str = "—") -> None:
    """Render the Bloomberg-style top status bar."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M:%S UTC")
    entity_display = html.escape(entity.upper() if entity != "—" else "—")
    st.markdown(
        f"""
        <div class="bb-topbar">
            <div class="bb-topbar-title">
                ▪ EXPLAINABLE FINANCIAL ANALYSIS SYSTEM
            </div>
            <div class="bb-topbar-right">
                <span><span class="bb-status-dot"></span>ONLINE</span>
                <span>ENTITY: <span class="bb-topbar-entity">{entity_display}</span></span>
                <span>{now}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Section header
# ─────────────────────────────────────────────────────────────────────────────

def render_section_header(title: str, subtitle: str = "") -> None:
    sub_html = (
        f'<div class="bb-section-sub">{html.escape(subtitle)}</div>'
        if subtitle
        else ""
    )
    st.markdown(
        f"""
        <div class="bb-section">
            <div class="bb-section-title">▶ {html.escape(title)}</div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Metric cards
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_value(v: float | None) -> str:
    """Format a numeric value for display."""
    if v is None:
        return "N/A"
    av = abs(v)
    if av >= 1_000_000:
        return f"{v / 1_000_000:,.2f}M"
    if av >= 1_000:
        return f"{v / 1_000:,.1f}K"
    return f"{v:,.2f}"


def _latest(ts: dict[str, Any], field: str) -> tuple[str, str]:
    """Return (formatted_value, period) for the most recent non-null entry."""
    series = ts.get(field) or []
    for item in reversed(series):
        if isinstance(item, dict) and item.get("value") is not None:
            return _fmt_value(float(item["value"])), str(item.get("period", "—"))
    return "N/A", "—"


def render_metric_cards(payload: dict[str, Any]) -> None:
    """Render four key metric cards from the OCR payload."""
    ts = payload.get("time_series") or {}

    cards = [
        ("revenue",           "REVENUE",           ""),
        ("total_assets",      "TOTAL ASSETS",       "cyan"),
        ("total_liabilities", "TOTAL LIABILITIES",  "red"),
        ("equity",            "EQUITY",             "green"),
    ]

    # Use native columns to avoid Markdown code-block detection on indented HTML
    cols = st.columns(4)
    for col, (field, label, cls) in zip(cols, cards):
        value, period = _latest(ts, field)
        col.markdown(
            f'<div class="bb-metric-card {cls}">'
            f'<div class="bb-metric-label">{label}</div>'
            f'<div class="bb-metric-value">{html.escape(value)}</div>'
            f'<div class="bb-metric-period">{html.escape(period)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Agent cards
# ─────────────────────────────────────────────────────────────────────────────

def _flat_metrics_rows(metrics: dict[str, Any]) -> str:
    """Render a flat metrics dict as table rows HTML."""
    rows = []
    for k, v in metrics.items():
        key_label = k.replace("_", " ").upper()
        if isinstance(v, float):
            val_str = f"{v:.4f}" if abs(v) < 100 else f"{v:,.2f}"
        elif isinstance(v, dict):
            continue  # skip nested (handled separately)
        else:
            val_str = str(v)
        rows.append(
            f'<div class="bb-metric-row">'
            f'<span class="bb-mkey">{html.escape(key_label)}</span>'
            f'<span class="bb-mval">{html.escape(val_str)}</span>'
            f"</div>"
        )
    return "".join(rows)


def render_agent_card(
    title: str,
    output: dict[str, Any],
    css_variant: str = "",   # "", "liq", "bs", "xref"
    icon: str = "◆",
) -> None:
    """Render a Bloomberg-style terminal card for a single agent result."""
    card_class = f"bb-agent-card {css_variant}".strip()

    # ── Error / skip ──────────────────────────────────────────
    if isinstance(output.get("error"), str):
        msg = html.escape(output["error"])
        st.markdown(
            f'<div class="bb-skip-card"><strong>⚠ {html.escape(title).upper()}</strong>'
            f" — {msg}</div>",
            unsafe_allow_html=True,
        )
        return

    # ── Success ───────────────────────────────────────────────
    metrics = output.get("metrics") or {}
    analysis = output.get("analysis") or ""

    # For cross-reference the metrics dict is nested; skip flat rendering.
    if metrics and not any(isinstance(v, dict) for v in metrics.values()):
        metric_rows_html = _flat_metrics_rows(metrics)
    else:
        metric_rows_html = ""

    # Render card frame + metrics (keep single-line to avoid Markdown code-block detection)
    st.markdown(
        f'<div class="{card_class}"><div class="bb-agent-title">{icon} {html.escape(title)}</div>{metric_rows_html}</div>',
        unsafe_allow_html=True,
    )

    # Render analysis separately — replace newlines with <br> so blank lines
    # inside LLM output don't break the Markdown HTML block parser
    if analysis:
        escaped = html.escape(analysis).replace("\n", "<br>")
        st.markdown(
            f'<div class="bb-analysis">{escaped}</div>',
            unsafe_allow_html=True,
        )


def render_cross_ref_card(output: dict[str, Any]) -> None:
    """Dedicated renderer for the Cross Reference Agent (nested metrics, long analysis)."""
    if isinstance(output.get("error"), str):
        msg = html.escape(output["error"])
        st.markdown(
            f'<div class="bb-skip-card"><strong>⚠ CROSS REFERENCE AGENT</strong> — {msg}</div>',
            unsafe_allow_html=True,
        )
        return

    analysis = output.get("analysis") or ""
    nested = output.get("metrics") or {}

    # Summarise each sub-agent's key metric
    summary_rows = ""
    colours = {
        "revenue": "#FFB000",
        "liquidity": "#00BFFF",
        "balance_sheet": "#FF6B35",
        "sentiment": "#CC88FF",
    }
    for key, colour in colours.items():
        sub = nested.get(key) or {}
        if not sub:
            continue
        # Pick the most representative metric
        representative = {
            "revenue":       ("cagr", "CAGR"),
            "liquidity":     ("liquidity_risk_flag", "LIQUIDITY RISK"),
            "balance_sheet": ("balance_sheet_risk",  "BS RISK"),
            "sentiment":     ("dominant_sentiment",  "PUBLIC SENTIMENT"),
        }.get(key, (None, ""))
        field, label = representative
        val = sub.get(field, "—") if field else "—"
        if isinstance(val, float):
            val_str = f"{val:.2f}"
        else:
            val_str = str(val)
        summary_rows += (
            f'<div class="bb-metric-row">'
            f'<span class="bb-mkey" style="color:{colour};">{key.replace("_"," ").upper()} — {label}</span>'
            f'<span class="bb-mval">{html.escape(val_str)}</span>'
            f"</div>"
        )

    # Render card frame + summary rows
    st.markdown(
        f'<div class="bb-agent-card xref"><div class="bb-agent-title">◈ CROSS REFERENCE AGENT — INTEGRATED ANALYSIS</div>{summary_rows}</div>',
        unsafe_allow_html=True,
    )

    # Render analysis separately — replace newlines with <br> so blank lines
    # inside LLM output don't break the Markdown HTML block parser
    if analysis:
        escaped = html.escape(analysis).replace("\n", "<br>")
        st.markdown(
            f'<div class="bb-analysis">{escaped}</div>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Workflow graph tooltip helpers
# ─────────────────────────────────────────────────────────────────────────────

def agent_tooltip_html(name: str, output: dict[str, Any] | None) -> str:
    """Build an HTML tooltip string for use as a vis.js node title."""
    if not output:
        return f"<b>{name}</b><br><i>Not yet run</i>"

    if isinstance(output.get("error"), str):
        err = output["error"][:120]
        return f"<b>{name}</b><br><span style='color:#FF7777'>⚠ {err}</span>"

    metrics = output.get("metrics") or {}
    lines = [f"<b style='color:#FFB000'>{name}</b>", ""]

    for k, v in metrics.items():
        if isinstance(v, dict):
            continue
        if isinstance(v, float):
            val_str = f"{v:.3f}" if abs(v) < 100 else f"{v:,.0f}"
        else:
            val_str = str(v)
        label = k.replace("_", " ").upper()
        lines.append(f"<b>{label}:</b> {val_str}")

    analysis = output.get("analysis")
    if isinstance(analysis, str) and analysis:
        # First 160 chars of the analysis
        snippet = analysis[:160] + ("…" if len(analysis) > 160 else "")
        lines += ["", f"<i style='color:#AAAAAA'>{snippet}</i>"]

    return "<br>".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Divider
# ─────────────────────────────────────────────────────────────────────────────

def render_hr() -> None:
    st.markdown('<div class="bb-hr"></div>', unsafe_allow_html=True)
