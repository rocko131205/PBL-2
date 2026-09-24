"""Credit Memo assembly + printable export (V3, Phase 4).

Pulls the whole analysis together into a single lender-style credit memo:
borrower profile, financial highlights, credit grade, debt serviceability,
strengths/risks, and a recommendation. Renders to a self-contained, printable
HTML document (the user prints to PDF from the browser — no heavy PDF dependency).
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from shared.formatting import format_money, format_percent, format_ratio
from shared.schema import NormalizedCompanyRecord


class CreditMemo(BaseModel):
    entity_id: str
    date: str
    currency: Optional[str] = None
    industry: Optional[str] = None
    grade: str = "NR"
    grade_label: str = "Not Rated"
    pd_band: str = "n/a"
    composite_score: Optional[float] = None
    highlights: List[Dict[str, str]] = Field(default_factory=list)   # [{label, value}]
    dscr_summary: Optional[Dict[str, Any]] = None
    strengths: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    recommendation: str = ""
    data_coverage_pct: Optional[float] = None
    disclaimer: str = (
        "This memo is decision-support for a qualified analyst. It is not a loan approval, "
        "rejection, or binding credit decision. All figures are computed deterministically; "
        "narrative text is generated from those figures."
    )


def _revenue_growth(record: NormalizedCompanyRecord) -> Optional[float]:
    rev = sorted(record.revenue, key=lambda x: x.period)
    if len(rev) < 2 or abs(rev[-2].value) < 1e-9:
        return None
    return (rev[-1].value - rev[-2].value) / abs(rev[-2].value) * 100.0


def build_memo(
    record: NormalizedCompanyRecord,
    scorecard: Any,                       # CreditScorecard
    min_dscr: Optional[float] = None,
    dscr_risk: Optional[str] = None,
    strengths: Optional[List[str]] = None,
    risks: Optional[List[str]] = None,
    recommendation: str = "",
) -> CreditMemo:
    ccy = record.currency
    rev = record.latest_value("revenue")
    op = record.latest_value("operating_income")
    ni = record.latest_value("net_income")
    ca, cl = record.latest_value("current_assets"), record.latest_value("current_liabilities")
    debt = record.latest_value("total_debt") or record.latest_value("total_liabilities")
    eq = record.latest_value("equity")

    def pct(n, d):
        return (n / d * 100.0) if (n is not None and d not in (None, 0)) else None

    def ratio(n, d):
        return (n / d) if (n is not None and d not in (None, 0)) else None

    highlights = [
        {"label": "Revenue (latest)", "value": format_money(rev, ccy)},
        {"label": "Revenue growth (YoY)", "value": format_percent(_revenue_growth(record))},
        {"label": "Operating margin", "value": format_percent(pct(op, rev))},
        {"label": "Net margin", "value": format_percent(pct(ni, rev))},
        {"label": "Current ratio", "value": format_ratio(ratio(ca, cl))},
        {"label": "Debt / Equity", "value": format_ratio(ratio(debt, eq))},
    ]

    dscr_summary = None
    if min_dscr is not None:
        dscr_summary = {"min_dscr": round(min_dscr, 2), "risk": dscr_risk or ""}

    return CreditMemo(
        entity_id=record.entity_id,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        currency=ccy,
        industry=record.industry,
        grade=getattr(scorecard, "grade", "NR"),
        grade_label=getattr(scorecard, "grade_label", "Not Rated"),
        pd_band=getattr(scorecard, "pd_band", "n/a"),
        composite_score=getattr(scorecard, "composite_score", None),
        highlights=highlights,
        dscr_summary=dscr_summary,
        strengths=strengths or [],
        risks=risks or [],
        recommendation=recommendation,
        data_coverage_pct=round(getattr(scorecard, "covered_weight", 0) * 100, 0),
    )


_GRADE_COLORS = {"AA": "#0a7", "A": "#0a7", "BBB": "#08a", "BB": "#c90",
                 "B": "#d60", "CCC": "#c00", "D": "#c00", "NR": "#888"}


def render_memo_html(memo: CreditMemo) -> str:
    """Return a self-contained, printable HTML document for the memo."""
    e = html.escape
    color = _GRADE_COLORS.get(memo.grade, "#888")

    highlight_rows = "".join(
        f'<tr><td>{e(h["label"])}</td><td class="num">{e(h["value"])}</td></tr>'
        for h in memo.highlights
    )
    strengths = "".join(f"<li>{e(s)}</li>" for s in memo.strengths) or "<li>—</li>"
    risks = "".join(f"<li>{e(r)}</li>" for r in memo.risks) or "<li>—</li>"

    dscr_block = ""
    if memo.dscr_summary:
        dscr_block = (
            f'<div class="kv"><span>Minimum DSCR</span>'
            f'<b>{memo.dscr_summary["min_dscr"]:.2f}x</b> '
            f'<span class="muted">({e(str(memo.dscr_summary["risk"]))})</span></div>'
        )

    coverage = f'<span class="muted">Data coverage: {memo.data_coverage_pct:.0f}%</span>' if memo.data_coverage_pct is not None else ""
    composite = f'{memo.composite_score:.0f}/100' if memo.composite_score is not None else "—"
    recommendation = e(memo.recommendation) if memo.recommendation else "Narrative not generated (LLM unavailable)."

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Credit Memo — {e(memo.entity_id)}</title>
<style>
  @media print {{ .noprint {{ display:none; }} }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         color:#1a1a1a; max-width:800px; margin:24px auto; padding:0 24px; line-height:1.5; }}
  h1 {{ font-size:22px; margin:0 0 2px 0; }}
  .sub {{ color:#666; font-size:13px; margin-bottom:16px; }}
  .grade {{ display:inline-block; border:2px solid {color}; color:{color}; border-radius:8px;
            padding:10px 18px; text-align:center; }}
  .grade .g {{ font-size:34px; font-weight:800; line-height:1; }}
  .grade .l {{ font-size:12px; }}
  .row {{ display:flex; gap:24px; align-items:center; margin:14px 0 20px; }}
  h2 {{ font-size:14px; text-transform:uppercase; letter-spacing:.06em; color:#444;
        border-bottom:1px solid #ddd; padding-bottom:4px; margin:22px 0 10px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  td {{ padding:5px 0; border-bottom:1px solid #f0f0f0; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }}
  .kv {{ font-size:14px; margin:4px 0; }} .kv b {{ font-size:16px; }}
  .muted {{ color:#888; font-size:12px; }}
  ul {{ margin:6px 0; padding-left:20px; font-size:14px; }}
  .cols {{ display:flex; gap:28px; }} .cols>div {{ flex:1; }}
  .disc {{ color:#888; font-size:11px; font-style:italic; margin-top:24px;
           border-top:1px solid #eee; padding-top:10px; }}
  .btn {{ background:{color}; color:#fff; border:none; padding:8px 16px; border-radius:6px;
          cursor:pointer; font-size:13px; }}
</style></head><body>
<button class="btn noprint" onclick="window.print()">🖨 Print / Save as PDF</button>
<h1>Credit Memo — {e(memo.entity_id)}</h1>
<div class="sub">{e(memo.industry or "Industry n/a")} · {e(memo.currency or "")} · {e(memo.date)}</div>
<div class="row">
  <div class="grade"><div class="g">{e(memo.grade)}</div><div class="l">{e(memo.grade_label)}</div></div>
  <div>
    <div class="kv"><span>Composite score</span> <b>{composite}</b></div>
    <div class="kv"><span>Est. default probability</span> <b>{e(memo.pd_band)}</b></div>
    {dscr_block}
    <div>{coverage}</div>
  </div>
</div>
<h2>Financial Highlights</h2>
<table>{highlight_rows}</table>
<div class="cols">
  <div><h2>Strengths</h2><ul>{strengths}</ul></div>
  <div><h2>Key Risks</h2><ul>{risks}</ul></div>
</div>
<h2>Assessment</h2>
<p style="font-size:14px;">{recommendation}</p>
<div class="disc">{e(memo.disclaimer)}</div>
</body></html>"""
