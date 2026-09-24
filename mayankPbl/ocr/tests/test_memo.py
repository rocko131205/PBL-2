"""V3 Phase 4 — credit memo tests."""
from __future__ import annotations

from shared.schema import NormalizedCompanyRecord, FinancialPeriod
from analysis.engines.credit_scorecard import compute_scorecard
from analysis.engines.credit_memo import build_memo, render_memo_html


def _rec(**latest):
    r = NormalizedCompanyRecord(entity_id="Acme <Corp>", source="test", currency="USD", industry="Software")
    for k, v in latest.items():
        setattr(r, k, [FinancialPeriod(period="2023-FY", value=v)])
    return r


def _full_rec():
    r = _rec(operating_income=250, net_income=180, equity=900, interest_expense=20,
             ebitda=300, total_debt=200, cash_and_equivalents=150,
             current_assets=600, current_liabilities=200)
    r.revenue = [FinancialPeriod(period="2022-FY", value=800), FinancialPeriod(period="2023-FY", value=1000)]
    return r


class TestBuildMemo:
    def test_core_fields(self):
        r = _full_rec()
        sc = compute_scorecard(r, industry="Software", min_dscr=2.2)
        memo = build_memo(r, sc, min_dscr=2.2, dscr_risk="LOW",
                          strengths=["Strong margins"], risks=["Concentrated revenue"],
                          recommendation="Proceed with standard covenants.")
        assert memo.entity_id == "Acme <Corp>"
        assert memo.grade == sc.grade
        assert memo.dscr_summary["min_dscr"] == 2.2
        assert len(memo.highlights) == 6
        assert memo.strengths and memo.risks

    def test_no_dscr(self):
        r = _full_rec()
        sc = compute_scorecard(r, industry="Software")
        memo = build_memo(r, sc)
        assert memo.dscr_summary is None


class TestRenderHtml:
    def test_html_contains_key_parts(self):
        r = _full_rec()
        sc = compute_scorecard(r, industry="Software", min_dscr=2.2)
        memo = build_memo(r, sc, min_dscr=2.2, dscr_risk="LOW", recommendation="OK.")
        out = render_memo_html(memo)
        assert out.startswith("<!DOCTYPE html>")
        assert "Credit Memo" in out
        assert memo.grade in out
        assert "Financial Highlights" in out
        assert "window.print()" in out

    def test_html_escapes_entity(self):
        r = _full_rec()
        sc = compute_scorecard(r, industry="Software")
        out = render_memo_html(build_memo(r, sc))
        assert "Acme &lt;Corp&gt;" in out       # escaped
        assert "<Corp>" not in out.replace("&lt;Corp&gt;", "")  # no raw injection
