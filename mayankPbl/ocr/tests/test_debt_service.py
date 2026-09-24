"""V3 Phase 2 — advanced debt-service (DSCR schedule, amortization, stress) tests."""
from __future__ import annotations

from shared.schema import NormalizedCompanyRecord, FinancialPeriod
from analysis.engines.debt_service import (
    LoanTerms,
    build_amortization_schedule,
    resolve_numerator,
    compute_dscr_schedule,
)


def _rec(**series):
    r = NormalizedCompanyRecord(entity_id="Test", source="test", currency="USD")
    for k, v in series.items():
        setattr(r, k, [FinancialPeriod(period="2023-FY", value=v)])
    return r


class TestAmortization:
    def test_equal_installment_repays_principal(self):
        rows = build_amortization_schedule(LoanTerms(principal=1000, annual_rate_pct=10, tenure_years=5))
        assert len(rows) == 5
        # loan fully repaid: final closing balance ~ 0
        assert abs(rows[-1].closing_balance) < 1.0
        # total principal ~ loan amount
        assert abs(sum(r.principal for r in rows) - 1000) < 1.0

    def test_bullet_principal_at_maturity(self):
        rows = build_amortization_schedule(LoanTerms(principal=1000, annual_rate_pct=10, tenure_years=3, structure="bullet"))
        assert rows[0].principal == 0 and rows[1].principal == 0
        assert abs(rows[-1].principal - 1000) < 1e-6
        # interest is constant each year (balance unchanged until maturity)
        assert abs(rows[0].interest - 100) < 1e-6

    def test_moratorium_defers_principal(self):
        rows = build_amortization_schedule(LoanTerms(principal=1200, annual_rate_pct=12, tenure_years=4, moratorium_years=1))
        assert rows[0].principal == 0  # grace year: interest only
        assert rows[1].principal > 0
        assert abs(rows[-1].closing_balance) < 1.0

    def test_zero_interest(self):
        rows = build_amortization_schedule(LoanTerms(principal=1000, annual_rate_pct=0, tenure_years=4))
        assert all(abs(r.interest) < 1e-9 for r in rows)
        assert abs(sum(r.principal for r in rows) - 1000) < 1e-6


class TestNumerator:
    def test_ebitda_basis(self):
        r = _rec(ebitda=500)
        val, name = resolve_numerator(r, "ebitda")
        assert val == 500 and "EBITDA" in name

    def test_cfads_conservative(self):
        r = _rec(operating_cash_flow=400, interest_expense=50, capital_expenditure=-100)
        val, name = resolve_numerator(r, "cfads")
        # OCF 400 + interest 50 - capex 100 = 350
        assert val == 350
        assert "CFADS" in name

    def test_ocf_adds_back_interest(self):
        r = _rec(operating_cash_flow=400, interest_expense=50)
        val, _ = resolve_numerator(r, "ocf")
        assert val == 450

    def test_missing_returns_none(self):
        r = _rec(revenue=1000)
        val, _ = resolve_numerator(r, "ebitda")
        assert val is None


class TestDSCRSchedule:
    def test_min_and_avg_dscr(self):
        r = _rec(ebitda=300)
        res = compute_dscr_schedule(r, LoanTerms(principal=1000, annual_rate_pct=10, tenure_years=5), basis="ebitda")
        assert res.min_dscr is not None
        assert res.avg_dscr >= res.min_dscr
        assert len(res.dscr_by_year) == 5
        assert res.min_dscr_year is not None

    def test_risk_classification_low(self):
        r = _rec(ebitda=10000)  # huge earnings vs small loan -> strong coverage
        res = compute_dscr_schedule(r, LoanTerms(principal=1000, annual_rate_pct=8, tenure_years=5), basis="ebitda", run_stress=False)
        assert res.risk_level.value == "LOW"

    def test_stress_tests_present(self):
        r = _rec(ebitda=300)
        res = compute_dscr_schedule(r, LoanTerms(principal=1000, annual_rate_pct=10, tenure_years=5), basis="ebitda")
        scenarios = {s.scenario for s in res.stress_results}
        assert "revenue_-30pct" in scenarios
        assert "rate_+300bps" in scenarios

    def test_stress_reduces_dscr(self):
        r = _rec(ebitda=300)
        res = compute_dscr_schedule(r, LoanTerms(principal=1000, annual_rate_pct=10, tenure_years=5), basis="ebitda")
        base_min = res.min_dscr
        haircut30 = next(s for s in res.stress_results if s.scenario == "revenue_-30pct")
        assert haircut30.min_dscr < base_min

    def test_falls_back_when_basis_unavailable(self):
        r = _rec(operating_cash_flow=400, interest_expense=50)  # no ebitda
        res = compute_dscr_schedule(r, LoanTerms(principal=1000, annual_rate_pct=10, tenure_years=5), basis="ebitda", run_stress=False)
        assert res.numerator_value is not None  # used a fallback basis
        assert any("unavailable" in n for n in res.notes)

    def test_coverage_ratios(self):
        r = _rec(operating_income=200, interest_expense=40, ebitda=250, total_debt=500)
        res = compute_dscr_schedule(r, LoanTerms(principal=1000, annual_rate_pct=10, tenure_years=5), basis="ebitda", run_stress=False)
        assert res.interest_coverage == 5.0   # 200/40
        assert res.debt_to_ebitda == 2.0      # 500/250

    def test_insufficient_data(self):
        r = _rec(revenue=1000)  # nothing usable as numerator
        res = compute_dscr_schedule(r, LoanTerms(principal=1000, annual_rate_pct=10, tenure_years=5), basis="ebitda")
        assert res.min_dscr is None
        assert res.risk_level.value == "INSUFFICIENT_DATA"
