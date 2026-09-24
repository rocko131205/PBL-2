"""V3 Phase 5 — forecasting tests."""
from __future__ import annotations

from shared.schema import NormalizedCompanyRecord, FinancialPeriod
from analysis.engines.forecast import forecast_field, _cagr, _next_periods


def _rec_revenue(values):
    r = NormalizedCompanyRecord(entity_id="Test", source="test", currency="USD")
    r.revenue = [FinancialPeriod(period=f"{2020+i}-FY", value=v) for i, v in enumerate(values)]
    return r


class TestCagr:
    def test_doubling_over_one_interval(self):
        assert abs(_cagr(100, 200, 1) - 100.0) < 1e-6

    def test_flat(self):
        assert abs(_cagr(100, 100, 3) - 0.0) < 1e-6

    def test_invalid(self):
        assert _cagr(0, 100, 2) is None


class TestNextPeriods:
    def test_sequential(self):
        assert _next_periods("2023-FY", 3) == ["2024-FY", "2025-FY", "2026-FY"]


class TestForecast:
    def test_growing_revenue(self):
        fc = forecast_field(_rec_revenue([100, 120, 144]), "revenue", years=3)
        assert fc is not None
        assert fc.cagr_pct is not None and fc.cagr_pct > 0
        assert len(fc.points) == 3
        # base case keeps growing
        assert fc.points[-1].base > fc.historical[-1][1]
        # optimistic above base above pessimistic
        assert fc.points[0].optimistic > fc.points[0].base > fc.points[0].pessimistic

    def test_insufficient_history(self):
        assert forecast_field(_rec_revenue([100]), "revenue") is None

    def test_missing_field(self):
        r = _rec_revenue([100, 120])
        assert forecast_field(r, "ebitda") is None

    def test_scenarios_have_spread(self):
        fc = forecast_field(_rec_revenue([100, 110, 121]), "revenue", years=2)
        assert fc.optimistic_growth_pct > fc.base_growth_pct > fc.pessimistic_growth_pct
