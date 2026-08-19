"""FinVeritas V2 — Integration Tests

Tests the full pipeline end-to-end with synthetic data.
Validates:
  1. Full workflow executes without exceptions
  2. Fact ledger is produced with correct structure
  3. DSCR calculations are methodology-aware
  4. Risk dashboard aggregates all signals
  5. No hallucinated financial numbers appear in outputs
  6. Schema contracts are enforced
"""
from __future__ import annotations

import json
import unittest
from typing import Any, Dict

from src.dscr_engine import compute_dscr, dscr_to_fact_entry
from src.payload_mapper import payload_to_normalized_record
from src.profitability_calculator import compute_profitability_metrics
from src.report_generator import generate_report_sections
from src.risk_indicator_engine import build_risk_dashboard
from src.saas_engine import compute_saas_metrics
from src.schema import (
    CreditAssessmentReport,
    DSCRInputs,
    DSCRResult,
    FactLedgerEntry,
    FinancialFactLedger,
    NormalizedCompanyRecord,
    ProvenancedValue,
    RiskDashboard,
    RiskLevel,
)
from src.solvency_calculator import compute_solvency_metrics


# ── Synthetic Payloads ────────────────────────────────────────────────────────

def _make_public_saas_payload() -> Dict[str, Any]:
    """Simulate a public SaaS company (like Salesforce or Zoom)."""
    return {
        "entity": {
            "entity_id": "TestSaaS Inc.",
            "currency": "USD",
            "qualitative_context": "Management noted strong ARR growth of 32% YoY with expanding enterprise contracts.",
        },
        "time_series": {
            "revenue": [
                {"period": "2022-FY", "value": 800_000_000},
                {"period": "2023-FY", "value": 1_000_000_000},
                {"period": "2024-FY", "value": 1_250_000_000},
            ],
            "operating_income": [
                {"period": "2022-FY", "value": 60_000_000},
                {"period": "2023-FY", "value": 120_000_000},
                {"period": "2024-FY", "value": 187_500_000},
            ],
            "gross_profit": [
                {"period": "2022-FY", "value": 560_000_000},
                {"period": "2023-FY", "value": 720_000_000},
                {"period": "2024-FY", "value": 937_500_000},
            ],
            "net_income": [
                {"period": "2022-FY", "value": 40_000_000},
                {"period": "2023-FY", "value": 80_000_000},
                {"period": "2024-FY", "value": 125_000_000},
            ],
            "total_assets": [
                {"period": "2024-FY", "value": 3_000_000_000},
            ],
            "total_liabilities": [
                {"period": "2024-FY", "value": 1_200_000_000},
            ],
            "equity": [
                {"period": "2024-FY", "value": 1_800_000_000},
            ],
            "total_debt": [
                {"period": "2024-FY", "value": 500_000_000},
            ],
            "interest_expense": [
                {"period": "2024-FY", "value": 25_000_000},
            ],
            "current_assets": [
                {"period": "2024-FY", "value": 1_500_000_000},
            ],
            "current_liabilities": [
                {"period": "2024-FY", "value": 600_000_000},
            ],
            "cash_and_equivalents": [
                {"period": "2024-FY", "value": 800_000_000},
            ],
            "ebitda": [
                {"period": "2024-FY", "value": 250_000_000},
            ],
        },
    }


def _make_private_company_payload() -> Dict[str, Any]:
    """Simulate a private company with minimal data (CSV upload)."""
    return {
        "entity": {
            "entity_id": "Acme Pvt. Ltd.",
            "currency": "INR",
        },
        "time_series": {
            "revenue": [
                {"period": "2023-FY", "value": 50_000_000},
                {"period": "2024-FY", "value": 58_000_000},
            ],
            "total_assets": [
                {"period": "2024-FY", "value": 100_000_000},
            ],
            "total_liabilities": [
                {"period": "2024-FY", "value": 60_000_000},
            ],
            "equity": [
                {"period": "2024-FY", "value": 40_000_000},
            ],
        },
    }


# ── Test Classes ──────────────────────────────────────────────────────────────

class TestEndToEndPublicSaaS(unittest.TestCase):
    """Full pipeline test with a well-data'd SaaS company."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _make_public_saas_payload()
        cls.record = payload_to_normalized_record(cls.payload, "ticker")

    def test_normalized_record_has_all_fields(self):
        avail = self.record.available_fields()
        self.assertIn("revenue", avail)
        self.assertIn("operating_income", avail)
        self.assertIn("total_assets", avail)

    def test_profitability_metrics_computed(self):
        entries = compute_profitability_metrics(self.record)
        metrics = {e.metric for e in entries}
        self.assertIn("gross_margin", metrics)
        self.assertIn("operating_margin", metrics)
        self.assertIn("roe", metrics)

    def test_operating_margin_correct(self):
        entries = compute_profitability_metrics(self.record)
        om = next((e for e in entries if e.metric == "operating_margin"), None)
        self.assertIsNotNone(om)
        # 187.5M / 1250M = 15%
        self.assertAlmostEqual(om.value, 15.0, delta=0.1)

    def test_solvency_metrics_computed(self):
        entries = compute_solvency_metrics(self.record)
        metrics = {e.metric for e in entries}
        self.assertIn("debt_to_equity", metrics)
        self.assertIn("interest_coverage", metrics)

    def test_saas_metrics_use_actual_growth(self):
        entries = compute_saas_metrics(self.record)
        growth_entry = next((e for e in entries if e.metric == "saas_revenue_growth"), None)
        self.assertIsNotNone(growth_entry)
        # (1250 - 1000) / 1000 = 25%
        self.assertAlmostEqual(growth_entry.value, 25.0, delta=0.1)

    def test_dscr_uses_ebitda_when_available(self):
        dscr_inputs = DSCRInputs(
            existing_loan_principal_repayment=50_000_000,
            existing_loan_interest=25_000_000,
        )
        result = compute_dscr(self.record, dscr_inputs)
        self.assertIsNotNone(result.dscr_ratio)
        # EBITDA = 250M, Debt service = 75M → DSCR ≈ 3.33
        self.assertAlmostEqual(result.dscr_ratio, 250_000_000 / 75_000_000, delta=0.1)
        self.assertEqual(result.methodology.numerator_name, "EBITDA")

    def test_dscr_never_uses_revenue_as_proxy(self):
        # Even with debt inputs, DSCR should use EBITDA, not revenue
        dscr_inputs = DSCRInputs(existing_loan_principal_repayment=50_000_000)
        result = compute_dscr(self.record, dscr_inputs)
        self.assertNotEqual(result.methodology.numerator_name, "Revenue Proxy")
        # Should use EBITDA methodology, not a revenue-based proxy
        self.assertIn(result.methodology.numerator_name, ["EBITDA", "Operating Income"])

    def test_risk_dashboard_produced(self):
        all_entries = (
            compute_profitability_metrics(self.record)
            + compute_solvency_metrics(self.record)
            + compute_saas_metrics(self.record)
        )
        dashboard = build_risk_dashboard(self.record, all_entries)
        self.assertIsInstance(dashboard, RiskDashboard)
        self.assertTrue(len(dashboard.indicators) > 0)

    def test_healthy_company_gets_low_risk(self):
        all_entries = (
            compute_profitability_metrics(self.record)
            + compute_solvency_metrics(self.record)
            + compute_saas_metrics(self.record)
        )
        dashboard = build_risk_dashboard(self.record, all_entries)
        # Well-capitalized SaaS company should not be CRITICAL
        self.assertNotEqual(dashboard.overall_risk, RiskLevel.CRITICAL)

    def test_fact_ledger_schema(self):
        all_entries = compute_profitability_metrics(self.record)
        ledger = FinancialFactLedger(
            entity_id="TestSaaS Inc.",
            analysis_timestamp="2024-01-01T00:00:00Z",
            currency="USD",
            entries=all_entries,
        )
        self.assertEqual(ledger.entity_id, "TestSaaS Inc.")
        self.assertTrue(len(ledger.entries) > 0)
        for entry in ledger.entries:
            self.assertIsNotNone(entry.metric)
            self.assertIsNotNone(entry.formula)


class TestEndToEndPrivateCompany(unittest.TestCase):
    """Tests with minimal private company data."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _make_private_company_payload()
        cls.record = payload_to_normalized_record(cls.payload, "csv")

    def test_dscr_insufficient_data_without_ebitda(self):
        """Private company without EBITDA/operating income — DSCR should gracefully handle."""
        result = compute_dscr(self.record, DSCRInputs())
        # No debt service inputs or insufficient data → interpretation should mention insufficient
        self.assertTrue(
            "insufficient" in result.interpretation.lower() or "cannot" in result.interpretation.lower(),
            f"Unexpected interpretation: {result.interpretation}"
        )

    def test_dscr_with_debt_inputs_but_no_ebitda(self):
        """DSCR requested but no EBITDA/operating income available."""
        dscr_inputs = DSCRInputs(
            existing_loan_principal_repayment=5_000_000,
            existing_loan_interest=2_000_000,
        )
        result = compute_dscr(self.record, dscr_inputs)
        # Should report insufficient data, NOT use revenue * 0.20
        self.assertIsNone(result.dscr_ratio)
        self.assertEqual(result.risk_level, RiskLevel.INSUFFICIENT_DATA)

    def test_saas_metrics_with_limited_data(self):
        entries = compute_saas_metrics(self.record)
        # Should produce growth metric but not rule of 40 (no operating income)
        growth = next((e for e in entries if e.metric == "saas_revenue_growth"), None)
        self.assertIsNotNone(growth)
        # (58 - 50) / 50 = 16%
        self.assertAlmostEqual(growth.value, 16.0, delta=0.1)

    def test_risk_dashboard_with_sparse_data(self):
        all_entries = compute_profitability_metrics(self.record) + compute_solvency_metrics(self.record)
        dashboard = build_risk_dashboard(self.record, all_entries)
        self.assertIsInstance(dashboard, RiskDashboard)


class TestReportGenerator(unittest.TestCase):
    """Tests the report generator produces correct structure."""

    def test_report_sections_structure(self):
        report = CreditAssessmentReport(
            entity_id="Test Co.",
            analysis_date="2024-01-01T00:00:00Z",
            currency="USD",
            risk_classification=RiskLevel.MODERATE,
            recommendation_narrative="Test narrative",
        )
        sections = generate_report_sections(report)
        self.assertIn("executive_summary", sections)
        self.assertIn("financial_metrics", sections)
        self.assertIn("recommendation", sections)
        self.assertEqual(sections["executive_summary"]["overall_risk"], "MODERATE")


class TestNoHallucination(unittest.TestCase):
    """Critical tests: ensure no fabricated financial data."""

    def test_dscr_never_fabricates_with_revenue_proxy(self):
        """The most critical V2 test. V1 used revenue * 0.20 as fake EBITDA."""
        record = NormalizedCompanyRecord(entity_id="Test", currency="USD", source="test")
        record.revenue = [ProvenancedValue(value=100_000_000, period="2024-FY", source="test")]
        # NO operating_income, NO ebitda
        dscr_inputs = DSCRInputs(existing_loan_principal_repayment=10_000_000)
        result = compute_dscr(record, dscr_inputs)

        # MUST NOT produce a DSCR ratio
        self.assertIsNone(result.dscr_ratio)

        # MUST NOT use revenue as proxy
        self.assertNotEqual(result.methodology.numerator_name, "Revenue Proxy")
        self.assertNotEqual(result.numerator_value, 100_000_000 * 0.20)

    def test_saas_never_uses_hardcoded_margin(self):
        """V1 used hardcoded profit_margin_pct = 10.0."""
        record = NormalizedCompanyRecord(entity_id="Test", currency="USD", source="test")
        record.revenue = [
            ProvenancedValue(value=100_000_000, period="2023-FY", source="test"),
            ProvenancedValue(value=120_000_000, period="2024-FY", source="test"),
        ]
        # NO operating_income → cannot compute actual margin
        entries = compute_saas_metrics(record)

        # Rule of 40 should NOT be computable with a value (no margin data)
        r40 = next((e for e in entries if e.metric == "rule_of_40"), None)
        if r40 is not None and r40.value is not None:
            # If somehow computed, it should NOT use 10.0% as margin
            # Growth = 20%, if margin were hardcoded 10 then R40 = 30
            self.assertNotAlmostEqual(r40.value, 30.0, delta=0.5,
                msg="Rule of 40 appears to use hardcoded 10% margin")

    def test_fact_ledger_entries_have_formulas(self):
        """Every computed metric must document its formula — no magic numbers."""
        record = payload_to_normalized_record(_make_public_saas_payload(), "ticker")
        entries = compute_profitability_metrics(record)
        for entry in entries:
            self.assertIsNotNone(entry.formula, f"{entry.metric} missing formula")
            self.assertTrue(len(entry.formula) > 0, f"{entry.metric} has empty formula")


class TestDSCRMethodologies(unittest.TestCase):
    """Test that DSCR uses the correct methodology cascade."""

    def test_prefers_ebitda_over_operating_income(self):
        record = NormalizedCompanyRecord(entity_id="Test", currency="USD", source="test")
        record.ebitda = [ProvenancedValue(value=100, period="2024-FY", source="test")]
        record.operating_income = [ProvenancedValue(value=80, period="2024-FY", source="test")]
        dscr_inputs = DSCRInputs(existing_loan_principal_repayment=50)

        result = compute_dscr(record, dscr_inputs)
        self.assertEqual(result.methodology.numerator_name, "EBITDA")
        self.assertEqual(result.numerator_value, 100)

    def test_falls_back_to_operating_income(self):
        record = NormalizedCompanyRecord(entity_id="Test", currency="USD", source="test")
        record.operating_income = [ProvenancedValue(value=80, period="2024-FY", source="test")]
        dscr_inputs = DSCRInputs(existing_loan_principal_repayment=50)

        result = compute_dscr(record, dscr_inputs)
        self.assertIn("Operating Income", result.methodology.numerator_name)
        self.assertEqual(result.numerator_value, 80)

    def test_methodology_documents_limitations(self):
        record = NormalizedCompanyRecord(entity_id="Test", currency="USD", source="test")
        record.operating_income = [ProvenancedValue(value=80, period="2024-FY", source="test")]
        dscr_inputs = DSCRInputs(existing_loan_principal_repayment=50)

        result = compute_dscr(record, dscr_inputs)
        self.assertTrue(len(result.methodology.limitations) > 0)

    def test_proposed_loan_terms_compute_debt_service(self):
        record = NormalizedCompanyRecord(entity_id="Test", currency="USD", source="test")
        record.ebitda = [ProvenancedValue(value=1000, period="2024-FY", source="test")]
        dscr_inputs = DSCRInputs(
            proposed_loan_amount=10000,
            proposed_interest_rate=10.0,
            proposed_tenure_years=5,
        )

        result = compute_dscr(record, dscr_inputs)
        self.assertIsNotNone(result.dscr_ratio)
        # Proposed: principal = 10000/5 = 2000, interest = 10000 * 0.10 = 1000 → total = 3000
        # DSCR = 1000 / 3000 ≈ 0.33
        self.assertAlmostEqual(result.dscr_ratio, 1000 / 3000, delta=0.1)


if __name__ == "__main__":
    unittest.main()
