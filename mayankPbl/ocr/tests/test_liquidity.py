"""V3 — V2 liquidity engine tests."""
from src.schema import NormalizedCompanyRecord, FinancialPeriod
from src.liquidity_metrics import compute_liquidity_metrics


def _rec(**latest):
    r = NormalizedCompanyRecord(entity_id="T", source="t", currency="USD")
    for k, v in latest.items():
        setattr(r, k, [FinancialPeriod(period="2023-FY", value=v)])
    return r


def _by(entries, metric):
    return next((e for e in entries if e.metric == metric), None)


def test_current_ratio_healthy():
    e = _by(compute_liquidity_metrics(_rec(current_assets=600, current_liabilities=200)), "current_ratio")
    assert e.value == 3.0 and e.risk_signal.value == "PASS"


def test_current_ratio_below_one_fails():
    e = _by(compute_liquidity_metrics(_rec(current_assets=100, current_liabilities=200)), "current_ratio")
    assert e.value == 0.5 and e.risk_signal.value == "FAIL"


def test_negative_working_capital_flagged():
    e = _by(compute_liquidity_metrics(_rec(current_assets=100, current_liabilities=200)), "working_capital")
    assert e.value == -100 and e.risk_signal.value == "FAIL"


def test_cash_ratio():
    e = _by(compute_liquidity_metrics(_rec(current_assets=600, current_liabilities=200, cash_and_equivalents=150)), "cash_ratio")
    assert e.value == 0.75


def test_missing_data_insufficient():
    e = _by(compute_liquidity_metrics(_rec(current_assets=600)), "current_ratio")
    assert e.value is None
