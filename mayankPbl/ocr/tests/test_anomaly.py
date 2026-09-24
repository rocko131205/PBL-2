"""V3 Phase 8 — anomaly engine tests."""
from __future__ import annotations

from shared.schema import NormalizedCompanyRecord, FinancialPeriod
from analysis.engines.anomaly_engine import detect_anomalies


def _rec(**series):
    r = NormalizedCompanyRecord(entity_id="Test", source="test", currency="USD")
    for field, pairs in series.items():
        setattr(r, field, [FinancialPeriod(period=p, value=v) for p, v in pairs])
    return r


class TestAnomalies:
    def test_large_swing_flagged(self):
        r = _rec(revenue=[("2022-FY", 100), ("2023-FY", 300)])  # +200%
        report = detect_anomalies(r)
        assert any(a.kind == "large_swing" and a.field == "revenue" for a in report.anomalies)

    def test_small_change_not_flagged(self):
        r = _rec(revenue=[("2022-FY", 100), ("2023-FY", 105)])  # +5%
        report = detect_anomalies(r)
        assert not any(a.kind == "large_swing" for a in report.anomalies)

    def test_sign_flip_to_negative(self):
        r = _rec(net_income=[("2022-FY", 50), ("2023-FY", -30)])
        report = detect_anomalies(r)
        flip = [a for a in report.anomalies if a.kind == "sign_flip" and a.field == "net_income"]
        assert flip and flip[0].severity == "warning"

    def test_impossible_negative_revenue_critical(self):
        r = _rec(revenue=[("2023-FY", -100)])
        report = detect_anomalies(r)
        assert report.critical_count >= 1
        assert any(a.kind == "impossible_value" for a in report.anomalies)

    def test_identity_break_flagged(self):
        r = _rec(total_assets=[("2023-FY", 1000)],
                 total_liabilities=[("2023-FY", 400)],
                 equity=[("2023-FY", 300)])  # 400+300=700 vs 1000 -> 30% gap
        report = detect_anomalies(r)
        assert any(a.kind == "identity_break" for a in report.anomalies)

    def test_balanced_sheet_ok(self):
        r = _rec(total_assets=[("2023-FY", 1000)],
                 total_liabilities=[("2023-FY", 600)],
                 equity=[("2023-FY", 400)])  # ties exactly
        report = detect_anomalies(r)
        assert not any(a.kind == "identity_break" for a in report.anomalies)

    def test_clean_company_no_anomalies(self):
        r = _rec(revenue=[("2022-FY", 100), ("2023-FY", 110)],
                 net_income=[("2022-FY", 20), ("2023-FY", 22)])
        report = detect_anomalies(r)
        assert report.critical_count == 0 and report.warning_count == 0

    def test_severity_ordering(self):
        r = _rec(revenue=[("2022-FY", 100), ("2023-FY", -300)])  # swing + impossible
        report = detect_anomalies(r)
        if len(report.anomalies) >= 2:
            assert report.anomalies[0].severity == "critical"
