"""V3 Phase 1 — data foundation tests (currency, formatting, cash flow, completeness)."""
from __future__ import annotations

from src.schema import NormalizedCompanyRecord, FinancialPeriod
from src.currency import get_fx_rate, normalize_record_currency
from src.formatting import format_money, format_ratio, format_percent, currency_symbol
from src.payload_mapper import payload_to_normalized_record


def _rec(currency="USD", **series):
    r = NormalizedCompanyRecord(entity_id="Test", source="test", currency=currency)
    for k, v in series.items():
        setattr(r, k, [FinancialPeriod(period="2023-FY", value=v)])
    return r


class TestFxRate:
    def test_identity(self):
        rate, source = get_fx_rate("USD", "USD", live=False)
        assert rate == 1.0 and source == "identity"

    def test_static_inr_to_usd(self):
        rate, source = get_fx_rate("INR", "USD", live=False)
        assert source == "static"
        assert 0.005 < rate < 0.05  # ~0.012

    def test_unknown_currency(self):
        rate, source = get_fx_rate("XYZ", "USD", live=False)
        assert rate is None and source == "unavailable"


class TestCurrencyNormalization:
    def test_same_currency_flagged_not_changed(self):
        r = _rec("USD", revenue=100.0)
        out = normalize_record_currency(r, "USD", live=False)
        assert out.is_currency_normalized is True
        assert out.latest_value("revenue") == 100.0
        assert out.fx_rate_used == 1.0

    def test_inr_converted_to_usd(self):
        r = _rec("INR", revenue=1000.0, total_assets=5000.0)
        out = normalize_record_currency(r, "USD", live=False)
        assert out.is_currency_normalized is True
        assert out.currency == "USD"
        assert out.original_currency == "INR"
        # revenue should shrink (INR worth less than USD)
        assert out.latest_value("revenue") < 1000.0
        # both monetary fields scaled by the same rate
        assert abs(out.latest_value("revenue") / 1000.0
                   - out.latest_value("total_assets") / 5000.0) < 1e-9

    def test_unconvertible_currency_left_unflagged(self):
        r = _rec("XYZ", revenue=100.0)
        out = normalize_record_currency(r, "USD", live=False)
        assert out.is_currency_normalized is False  # caller must warn
        assert out.latest_value("revenue") == 100.0


class TestFormatting:
    def test_billions(self):
        assert format_money(256_345_567_000, "INR") == "₹256.35B"

    def test_millions_and_symbol(self):
        assert format_money(1_200_000, "USD") == "$1.20M"

    def test_thousands(self):
        assert format_money(4_500, "USD") == "$4.50K"

    def test_negative(self):
        assert format_money(-4_500_000, "USD") == "-$4.50M"

    def test_none(self):
        assert format_money(None) == "N/A"

    def test_small_value_no_suffix(self):
        assert format_money(250, "USD") == "$250.00"

    def test_ratio_and_percent(self):
        assert format_ratio(1.853) == "1.85x"
        assert format_percent(42.53) == "42.5%"
        assert format_ratio(None) == "N/A"

    def test_symbol_fallback(self):
        assert currency_symbol("ZZZ") == "ZZZ "


class TestCashFlowIngestion:
    def test_cashflow_fields_mapped(self):
        payload = {
            "entity": {"entity_id": "CF Co", "currency": "USD"},
            "time_series": {
                "revenue": [{"period": "2023-FY", "value": 100}],
                "operating_cash_flow": [{"period": "2023-FY", "value": 30}],
                "capital_expenditure": [{"period": "2023-FY", "value": -10}],
                "free_cash_flow": [{"period": "2023-FY", "value": 20}],
            },
        }
        rec = payload_to_normalized_record(payload, "ticker")
        assert rec.latest_value("operating_cash_flow") == 30
        assert rec.latest_value("capital_expenditure") == -10
        assert rec.latest_value("free_cash_flow") == 20


class TestCompleteness:
    def test_completeness_report(self):
        rec = _rec("USD", revenue=100.0, operating_cash_flow=20.0)
        c = rec.completeness()
        assert "revenue" in c["present"]
        assert "operating_cash_flow" in c["present"]
        assert c["present_count"] == 2
        assert 0 < c["score"] < 100
