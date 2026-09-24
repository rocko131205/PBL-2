"""V3 — reporting-scale detection & rescale tests."""
from finveritas.ingestion.scale import detect_scale, rescale_payload, SCALE_MULTIPLIERS


class TestDetect:
    def test_millions(self):
        assert detect_scale("Consolidated Balance Sheet (₹ in millions)") == (1e6, "million")

    def test_crore(self):
        assert detect_scale("All figures in Rs. Crore unless stated") == (1e7, "crore")

    def test_lakh(self):
        assert detect_scale("Amounts in lakhs") == (1e5, "lakh")

    def test_thousand(self):
        assert detect_scale("in thousands of USD") == (1e3, "thousand")

    def test_none_defaults_absolute(self):
        assert detect_scale("Balance Sheet as at 31 March") == (1.0, "absolute")

    def test_empty(self):
        assert detect_scale("") == (1.0, "absolute")


class TestRescale:
    def _payload(self):
        return {
            "entity": {"entity_id": "Infosys", "currency": "INR"},
            "time_series": {
                "revenue": [{"period": "2024-FY", "value": 1_489_030.0}],
                "equity": [{"period": "2024-FY", "value": 962_030.0}],
            },
        }

    def test_millions_rescaled_to_absolute(self):
        out = rescale_payload(self._payload(), 1e6)
        # 1,489,030 (in millions) -> 1.48903e12 absolute (= ₹1,48,903 crore)
        assert out["time_series"]["revenue"][0]["value"] == 1_489_030.0 * 1e6
        assert out["entity"]["reported_scale_multiplier"] == 1e6

    def test_identity_unchanged(self):
        out = rescale_payload(self._payload(), 1.0)
        assert out["time_series"]["revenue"][0]["value"] == 1_489_030.0

    def test_original_not_mutated(self):
        p = self._payload()
        rescale_payload(p, 1e6)
        assert p["time_series"]["revenue"][0]["value"] == 1_489_030.0  # deep-copied

    def test_multiplier_table(self):
        assert SCALE_MULTIPLIERS["crore"] == 1e7
