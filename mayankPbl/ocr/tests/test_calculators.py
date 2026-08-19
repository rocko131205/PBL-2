"""Unit tests for the FinVeritas V2 deterministic calculators.

Tests each calculator with known inputs and expected outputs to ensure:
1. Financial calculations are mathematically correct
2. Insufficient data is explicitly flagged (never fabricated)
3. Risk classifications are deterministic and consistent
4. DSCR never uses hardcoded proxies
5. SaaS metrics use actual data
"""
from __future__ import annotations

import pytest

from src.schema import (
    CheckStatus,
    DSCRInputs,
    DSCRResult,
    FactLedgerEntry,
    FactStatus,
    FinancialPeriod,
    NormalizedCompanyRecord,
    RiskLevel,
)


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _make_record(**kwargs) -> NormalizedCompanyRecord:
    """Create a NormalizedCompanyRecord with defaults overridden."""
    defaults = dict(
        entity_id="TestCorp",
        source="test",
        currency="USD",
    )
    defaults.update(kwargs)
    return NormalizedCompanyRecord(**defaults)


def _fp(period: str, value: float) -> FinancialPeriod:
    return FinancialPeriod(period=period, value=value)


def _find_entry(entries: list[FactLedgerEntry], metric: str) -> FactLedgerEntry | None:
    for e in entries:
        if e.metric == metric:
            return e
    return None


# =========================================================================
# Test: Profitability Calculator
# =========================================================================

class TestProfitabilityCalculator:
    def test_gross_margin_calculated(self):
        from src.profitability_calculator import compute_profitability_metrics

        record = _make_record(
            revenue=[_fp("2023-FY", 1000)],
            gross_profit=[_fp("2023-FY", 700)],
        )
        entries = compute_profitability_metrics(record)
        gm = _find_entry(entries, "gross_margin")
        assert gm is not None
        assert gm.value == 70.0
        assert gm.status == FactStatus.VALID
        assert gm.unit == "%"

    def test_gross_margin_insufficient_data(self):
        from src.profitability_calculator import compute_profitability_metrics

        record = _make_record(
            revenue=[_fp("2023-FY", 1000)],
            # No gross_profit
        )
        entries = compute_profitability_metrics(record)
        gm = _find_entry(entries, "gross_margin")
        assert gm is not None
        assert gm.value is None
        assert gm.status == FactStatus.INSUFFICIENT_DATA

    def test_operating_margin(self):
        from src.profitability_calculator import compute_profitability_metrics

        record = _make_record(
            revenue=[_fp("2023-FY", 1000)],
            operating_income=[_fp("2023-FY", 200)],
        )
        entries = compute_profitability_metrics(record)
        om = _find_entry(entries, "operating_margin")
        assert om is not None
        assert om.value == 20.0

    def test_negative_operating_margin_flagged(self):
        from src.profitability_calculator import compute_profitability_metrics

        record = _make_record(
            revenue=[_fp("2023-FY", 1000)],
            operating_income=[_fp("2023-FY", -50)],
        )
        entries = compute_profitability_metrics(record)
        om = _find_entry(entries, "operating_margin")
        assert om is not None
        assert om.value == -5.0
        assert om.risk_signal == CheckStatus.FAIL

    def test_roe_calculation(self):
        from src.profitability_calculator import compute_profitability_metrics

        record = _make_record(
            net_income=[_fp("2023-FY", 150)],
            equity=[_fp("2023-FY", 500)],
        )
        entries = compute_profitability_metrics(record)
        roe = _find_entry(entries, "roe")
        assert roe is not None
        assert roe.value == 30.0

    def test_roa_calculation(self):
        from src.profitability_calculator import compute_profitability_metrics

        record = _make_record(
            net_income=[_fp("2023-FY", 100)],
            total_assets=[_fp("2023-FY", 2000)],
        )
        entries = compute_profitability_metrics(record)
        roa = _find_entry(entries, "roa")
        assert roa is not None
        assert roa.value == 5.0

    def test_roce_calculation(self):
        from src.profitability_calculator import compute_profitability_metrics

        record = _make_record(
            operating_income=[_fp("2023-FY", 300)],
            total_assets=[_fp("2023-FY", 2000)],
            current_liabilities=[_fp("2023-FY", 500)],
        )
        entries = compute_profitability_metrics(record)
        roce = _find_entry(entries, "roce")
        assert roce is not None
        # ROCE = 300 / (2000 - 500) = 20.0%
        assert roce.value == 20.0


# =========================================================================
# Test: Solvency Calculator
# =========================================================================

class TestSolvencyCalculator:
    def test_debt_to_equity(self):
        from src.solvency_calculator import compute_solvency_metrics

        record = _make_record(
            total_debt=[_fp("2023-FY", 600)],
            equity=[_fp("2023-FY", 400)],
        )
        entries = compute_solvency_metrics(record)
        d2e = _find_entry(entries, "debt_to_equity")
        assert d2e is not None
        assert d2e.value == 1.5
        assert d2e.risk_signal == CheckStatus.PASS

    def test_high_leverage_flagged(self):
        from src.solvency_calculator import compute_solvency_metrics

        record = _make_record(
            total_liabilities=[_fp("2023-FY", 3500)],
            equity=[_fp("2023-FY", 500)],
        )
        entries = compute_solvency_metrics(record)
        d2e = _find_entry(entries, "debt_to_equity")
        assert d2e is not None
        assert d2e.value == 7.0
        assert d2e.risk_signal == CheckStatus.FAIL

    def test_interest_coverage_strong(self):
        from src.solvency_calculator import compute_solvency_metrics

        record = _make_record(
            operating_income=[_fp("2023-FY", 500)],
            interest_expense=[_fp("2023-FY", 100)],
        )
        entries = compute_solvency_metrics(record)
        icr = _find_entry(entries, "interest_coverage")
        assert icr is not None
        assert icr.value == 5.0
        assert icr.risk_signal == CheckStatus.PASS

    def test_interest_coverage_weak(self):
        from src.solvency_calculator import compute_solvency_metrics

        record = _make_record(
            operating_income=[_fp("2023-FY", 80)],
            interest_expense=[_fp("2023-FY", 100)],
        )
        entries = compute_solvency_metrics(record)
        icr = _find_entry(entries, "interest_coverage")
        assert icr is not None
        assert icr.value == 0.8
        assert icr.risk_signal == CheckStatus.FAIL

    def test_net_debt_calculation(self):
        from src.solvency_calculator import compute_solvency_metrics

        record = _make_record(
            total_debt=[_fp("2023-FY", 1000)],
            cash_and_equivalents=[_fp("2023-FY", 300)],
            total_assets=[_fp("2023-FY", 2000)],
        )
        entries = compute_solvency_metrics(record)
        nd = _find_entry(entries, "net_debt")
        assert nd is not None
        assert nd.value == 700.0

    def test_net_cash_position(self):
        from src.solvency_calculator import compute_solvency_metrics

        record = _make_record(
            total_debt=[_fp("2023-FY", 200)],
            cash_and_equivalents=[_fp("2023-FY", 500)],
            total_assets=[_fp("2023-FY", 1000)],
        )
        entries = compute_solvency_metrics(record)
        nd = _find_entry(entries, "net_debt")
        assert nd is not None
        assert nd.value == -300.0  # net cash


# =========================================================================
# Test: DSCR Engine (CRITICAL — V1 was fake)
# =========================================================================

class TestDSCREngine:
    def test_dscr_with_ebitda(self):
        """DSCR should use EBITDA when available."""
        from src.dscr_engine import compute_dscr

        record = _make_record(
            ebitda=[_fp("2023-FY", 500)],
            revenue=[_fp("2023-FY", 2000)],
        )
        inputs = DSCRInputs(
            existing_loan_principal_repayment=100,
            existing_loan_interest=50,
        )
        result = compute_dscr(record, inputs)
        assert result.dscr_ratio is not None
        # DSCR = 500 / (100 + 50) = 3.33
        assert abs(result.dscr_ratio - 3.3333) < 0.01
        assert result.methodology.numerator_name == "EBITDA"
        assert result.risk_level == RiskLevel.LOW

    def test_dscr_falls_back_to_operating_income(self):
        """When EBITDA is unavailable, use Operating Income."""
        from src.dscr_engine import compute_dscr

        record = _make_record(
            operating_income=[_fp("2023-FY", 300)],
            revenue=[_fp("2023-FY", 2000)],
            # No EBITDA
        )
        inputs = DSCRInputs(
            existing_loan_principal_repayment=100,
            existing_loan_interest=50,
        )
        result = compute_dscr(record, inputs)
        assert result.dscr_ratio is not None
        # DSCR = 300 / 150 = 2.0
        assert abs(result.dscr_ratio - 2.0) < 0.01
        assert result.methodology.numerator_name == "Operating Income (EBIT)"

    def test_dscr_never_uses_revenue_proxy(self):
        """CRITICAL: DSCR must NEVER use revenue * 0.20 or any revenue proxy."""
        from src.dscr_engine import compute_dscr

        record = _make_record(
            revenue=[_fp("2023-FY", 2000)],
            # No EBITDA, no operating_income, no net_income
        )
        inputs = DSCRInputs(
            existing_loan_principal_repayment=100,
            existing_loan_interest=50,
        )
        result = compute_dscr(record, inputs)
        # Should NOT be able to calculate DSCR with only revenue
        assert result.dscr_ratio is None
        assert result.risk_level == RiskLevel.INSUFFICIENT_DATA
        # Verify it's NOT 2000 * 0.20 / 150 = 2.67 (the old fake calculation)
        assert result.numerator_value == 0.0

    def test_dscr_insufficient_data_clearly_stated(self):
        """When data is missing, DSCR should explicitly state what's needed."""
        from src.dscr_engine import compute_dscr

        record = _make_record(
            revenue=[_fp("2023-FY", 2000)],
        )
        inputs = DSCRInputs()
        result = compute_dscr(record, inputs)
        assert result.dscr_ratio is None
        assert "insufficient" in result.interpretation.lower() or "cannot" in result.interpretation.lower()

    def test_dscr_no_debt_service(self):
        """When no debt service is provided, explain what's needed."""
        from src.dscr_engine import compute_dscr

        record = _make_record(
            ebitda=[_fp("2023-FY", 500)],
        )
        inputs = DSCRInputs()  # No debt service
        result = compute_dscr(record, inputs)
        assert result.dscr_ratio is None
        assert "provide" in result.interpretation.lower() or "loan" in result.interpretation.lower()

    def test_dscr_calculated_from_loan_terms(self):
        """DSCR should calculate debt service from loan amount + rate + tenure."""
        from src.dscr_engine import compute_dscr

        record = _make_record(
            ebitda=[_fp("2023-FY", 500)],
        )
        inputs = DSCRInputs(
            proposed_loan_amount=1000,
            proposed_interest_rate=10.0,
            proposed_tenure_years=5.0,
        )
        result = compute_dscr(record, inputs)
        assert result.dscr_ratio is not None
        assert result.dscr_ratio > 0
        assert result.denominator_value > 0

    def test_dscr_methodology_documented(self):
        """Every DSCR result must include full methodology documentation."""
        from src.dscr_engine import compute_dscr

        record = _make_record(
            ebitda=[_fp("2023-FY", 500)],
        )
        inputs = DSCRInputs(
            existing_loan_principal_repayment=100,
            existing_loan_interest=50,
        )
        result = compute_dscr(record, inputs)
        assert result.methodology is not None
        assert result.methodology.numerator_name
        assert result.methodology.numerator_formula
        assert result.methodology.time_period

    def test_dscr_critical_risk_below_1(self):
        """DSCR below 1.0 must be classified as CRITICAL risk."""
        from src.dscr_engine import compute_dscr

        record = _make_record(
            ebitda=[_fp("2023-FY", 100)],
        )
        inputs = DSCRInputs(
            existing_loan_principal_repayment=80,
            existing_loan_interest=50,
        )
        result = compute_dscr(record, inputs)
        # DSCR = 100 / 130 = 0.77
        assert result.dscr_ratio is not None
        assert result.dscr_ratio < 1.0
        assert result.risk_level == RiskLevel.CRITICAL

    def test_dscr_reconstructed_from_components(self):
        """DSCR should reconstruct NOI from net_income + interest + dep + tax."""
        from src.dscr_engine import compute_dscr

        record = _make_record(
            net_income=[_fp("2023-FY", 200)],
            interest_expense=[_fp("2023-FY", 50)],
            depreciation=[_fp("2023-FY", 30)],
            income_tax=[_fp("2023-FY", 70)],
            # No EBITDA, no operating_income
        )
        inputs = DSCRInputs(
            existing_loan_principal_repayment=100,
            existing_loan_interest=50,
        )
        result = compute_dscr(record, inputs)
        assert result.dscr_ratio is not None
        # Reconstructed: 200 + 50 + 30 + 70 = 350
        # DSCR = 350 / 150 = 2.33
        assert abs(result.dscr_ratio - 2.3333) < 0.01
        assert "Reconstructed" in result.methodology.numerator_name


# =========================================================================
# Test: SaaS Engine (V1 was hardcoded)
# =========================================================================

class TestSaaSEngine:
    def test_rule_of_40_uses_actual_data(self):
        """Rule of 40 must use ACTUAL growth + margin, never hardcoded 10%."""
        from src.saas_engine import compute_saas_metrics

        record = _make_record(
            revenue=[_fp("2022-FY", 800), _fp("2023-FY", 1000)],
            operating_income=[_fp("2023-FY", 200)],
        )
        entries = compute_saas_metrics(record)
        r40 = _find_entry(entries, "saas_rule_of_40")
        assert r40 is not None
        # Growth = (1000-800)/800 * 100 = 25%
        # Op Margin = 200/1000 * 100 = 20%
        # Rule of 40 = 25 + 20 = 45
        assert r40.value == 45.0
        assert r40.status == FactStatus.VALID

    def test_rule_of_40_never_uses_hardcoded_margin(self):
        """Rule of 40 must NOT use profit_margin = 10.0 (the old V1 bug)."""
        from src.saas_engine import compute_saas_metrics

        record = _make_record(
            revenue=[_fp("2022-FY", 800), _fp("2023-FY", 1000)],
            # NO operating_income or gross_profit
        )
        entries = compute_saas_metrics(record)
        r40 = _find_entry(entries, "saas_rule_of_40")
        assert r40 is not None
        # Without any margin data, should be INSUFFICIENT or clearly marked ESTIMATED
        assert r40.status in (FactStatus.INSUFFICIENT_DATA, FactStatus.ESTIMATED)
        # Must NOT be 35.0 (25% growth + 10% hardcoded)
        if r40.value is not None:
            assert r40.value != 35.0

    def test_gross_margin_for_saas(self):
        from src.saas_engine import compute_saas_metrics

        record = _make_record(
            revenue=[_fp("2023-FY", 1000)],
            gross_profit=[_fp("2023-FY", 750)],
        )
        entries = compute_saas_metrics(record)
        gm = _find_entry(entries, "saas_gross_margin")
        assert gm is not None
        assert gm.value == 75.0
        assert gm.risk_signal == CheckStatus.PASS

    def test_low_gross_margin_flagged(self):
        from src.saas_engine import compute_saas_metrics

        record = _make_record(
            revenue=[_fp("2023-FY", 1000)],
            gross_profit=[_fp("2023-FY", 250)],
        )
        entries = compute_saas_metrics(record)
        gm = _find_entry(entries, "saas_gross_margin")
        assert gm is not None
        assert gm.value == 25.0
        assert gm.risk_signal == CheckStatus.WARN


# =========================================================================
# Test: Risk Indicator Engine
# =========================================================================

class TestRiskIndicatorEngine:
    def test_risk_dashboard_collects_signals(self):
        from src.risk_indicator_engine import build_risk_dashboard

        record = _make_record(
            revenue=[_fp("2022-FY", 1000), _fp("2023-FY", 900)],
            ebitda=[_fp("2023-FY", -50)],
            equity=[_fp("2023-FY", -100)],
        )
        # Create some fact entries with risk signals
        entries = [
            FactLedgerEntry(
                metric="operating_margin",
                display_name="Operating Margin",
                category="profitability",
                value=-5.0,
                unit="%",
                status=FactStatus.VALID,
                risk_signal=CheckStatus.FAIL,
                risk_detail="Negative margin",
            ),
        ]
        dashboard = build_risk_dashboard(record, entries)
        assert dashboard is not None
        assert len(dashboard.indicators) > 0
        assert dashboard.fail_count > 0

    def test_healthy_company_low_risk(self):
        from src.risk_indicator_engine import build_risk_dashboard

        record = _make_record(
            revenue=[_fp("2022-FY", 800), _fp("2023-FY", 1000)],
            ebitda=[_fp("2023-FY", 300)],
            equity=[_fp("2023-FY", 500)],
            net_income=[_fp("2022-FY", 100), _fp("2023-FY", 150)],
            current_assets=[_fp("2023-FY", 600)],
            current_liabilities=[_fp("2023-FY", 300)],
        )
        entries = [
            FactLedgerEntry(
                metric="operating_margin",
                display_name="Operating Margin",
                category="profitability",
                value=20.0,
                unit="%",
                status=FactStatus.VALID,
                risk_signal=CheckStatus.PASS,
                risk_detail="Healthy margin",
            ),
        ]
        dashboard = build_risk_dashboard(record, entries)
        assert dashboard.overall_risk in (RiskLevel.LOW, RiskLevel.MODERATE)


# =========================================================================
# Test: Schema Models
# =========================================================================

class TestSchema:
    def test_normalized_record_latest_value(self):
        record = _make_record(
            revenue=[_fp("2021-FY", 500), _fp("2022-FY", 700), _fp("2023-FY", 1000)],
        )
        assert record.latest_value("revenue") == 1000
        assert record.latest_value("ebitda") is None

    def test_normalized_record_available_fields(self):
        record = _make_record(
            revenue=[_fp("2023-FY", 1000)],
            total_assets=[_fp("2023-FY", 2000)],
        )
        avail = record.available_fields()
        assert "revenue" in avail
        assert "total_assets" in avail
        assert "ebitda" not in avail

    def test_dscr_inputs_total_debt_service(self):
        inputs = DSCRInputs(
            existing_loan_principal_repayment=100,
            existing_loan_interest=50,
            proposed_loan_principal_repayment=80,
            proposed_loan_interest=30,
        )
        assert inputs.total_annual_debt_service == 260


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
