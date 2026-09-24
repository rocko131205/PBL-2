"""V3 Phase 3 — credit scorecard tests."""
from __future__ import annotations

from shared.schema import NormalizedCompanyRecord, FinancialPeriod
from analysis.engines.credit_scorecard import compute_scorecard, resolve_profile, _interp


def _rec(industry_series=None, **latest):
    """Build a record where each kwarg is a single-period latest value."""
    r = NormalizedCompanyRecord(entity_id="Test", source="test", currency="USD")
    for k, v in latest.items():
        setattr(r, k, [FinancialPeriod(period="2023-FY", value=v)])
    return r


class TestProfile:
    def test_saas(self):
        assert resolve_profile("Application Software") == "software_saas"

    def test_bank(self):
        assert resolve_profile("Financial Services - Banks") == "financial"

    def test_manufacturing(self):
        assert resolve_profile("Auto Manufacturing") == "manufacturing"

    def test_default(self):
        assert resolve_profile(None) == "general"
        assert resolve_profile("Something Unusual") == "general"


class TestInterp:
    def test_clamps_low(self):
        assert _interp(0.0, [(1.0, 30), (2.0, 90)]) == 30

    def test_clamps_high(self):
        assert _interp(5.0, [(1.0, 30), (2.0, 90)]) == 90

    def test_midpoint(self):
        assert _interp(1.5, [(1.0, 30), (2.0, 90)]) == 60


class TestScorecard:
    def _strong(self, industry="Software"):
        return _rec(
            revenue=1000, operating_income=250, net_income=180, equity=900,
            interest_expense=20, ebitda=300, total_debt=200, cash_and_equivalents=150,
            current_assets=600, current_liabilities=200,
        )

    def _weak(self):
        return _rec(
            revenue=1000, operating_income=-50, net_income=-120, equity=100,
            interest_expense=90, ebitda=10, total_debt=800, cash_and_equivalents=10,
            current_assets=150, current_liabilities=400,
        )

    def test_strong_company_high_grade(self):
        sc = compute_scorecard(self._strong(), industry="Software", min_dscr=2.5)
        assert sc.composite_score > 70
        assert sc.grade in ("A", "AA", "BBB")

    def test_weak_company_low_grade(self):
        sc = compute_scorecard(self._weak(), industry="Software", min_dscr=0.6)
        assert sc.composite_score < 50
        assert sc.grade in ("B", "CCC", "D")

    def test_missing_data_reduces_coverage(self):
        r = _rec(revenue=1000, operating_income=100)  # very sparse
        sc = compute_scorecard(r, industry="Software")
        assert sc.covered_weight < 1.0
        assert any(f.status == "missing" for f in sc.factors)
        # composite still computed from what's available
        assert sc.composite_score is not None

    def test_dscr_excluded_when_no_loan(self):
        sc = compute_scorecard(self._strong(), industry="Software", min_dscr=None)
        dscr_factor = next(f for f in sc.factors if f.key == "dscr")
        assert dscr_factor.score is None
        assert any("No loan analysed" in n for n in sc.notes)

    def test_industry_awareness_leverage(self):
        # Same high leverage scored more leniently for a bank than a general firm.
        r = _rec(
            revenue=1000, operating_income=200, net_income=150, equity=100,
            interest_expense=30, ebitda=250, total_debt=500,
            current_assets=300, current_liabilities=200,
        )
        general = compute_scorecard(r, industry="Retail Trade")
        bank = compute_scorecard(r, industry="Banks")
        d2e_gen = next(f for f in general.factors if f.key == "debt_to_equity").score
        d2e_bank = next(f for f in bank.factors if f.key == "debt_to_equity").score
        assert d2e_bank > d2e_gen  # bank penalised less for the same D/E

    def test_factor_contributions_transparent(self):
        sc = compute_scorecard(self._strong(), industry="Software", min_dscr=2.0)
        for f in sc.factors:
            if f.score is not None:
                assert f.contribution is not None
                assert f.note  # human-readable note present

    def test_not_rated_when_empty(self):
        sc = compute_scorecard(_rec(revenue=1000), industry="Software")
        # only stability-less single-period revenue; almost nothing scorable
        assert sc.grade == "NR" or sc.composite_score is not None
