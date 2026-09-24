"""V3 — working-capital cycle tests."""
from finveritas.shared.schema import NormalizedCompanyRecord, FinancialPeriod
from finveritas.analysis.metrics.working_capital import compute_working_capital_cycle


def _rec(**latest):
    r = NormalizedCompanyRecord(entity_id="T", source="t", currency="USD")
    for k, v in latest.items():
        setattr(r, k, [FinancialPeriod(period="2023-FY", value=v)])
    return r


def _by(entries, m):
    return next((e for e in entries if e.metric == m), None)


def test_dso():
    # AR 100, revenue 365 -> DSO = 100 days
    e = _by(compute_working_capital_cycle(_rec(accounts_receivable=100, revenue=365)), "dso")
    assert round(e.value) == 100


def test_ccc_computed():
    r = _rec(accounts_receivable=100, revenue=365, inventory=50, cost_of_revenue=365, accounts_payable=73)
    entries = compute_working_capital_cycle(r)
    ccc = _by(entries, "cash_conversion_cycle")
    # DSO 100 + DIO 50 - DPO 73 = 77
    assert round(ccc.value) == 77
    assert ccc.risk_signal.value == "WARN"


def test_short_cycle_passes():
    r = _rec(accounts_receivable=10, revenue=365, inventory=5, cost_of_revenue=365, accounts_payable=10)
    ccc = _by(compute_working_capital_cycle(r), "cash_conversion_cycle")
    assert ccc.risk_signal.value == "PASS"


def test_missing_inventory_no_ccc():
    r = _rec(accounts_receivable=100, revenue=365)  # DSO only, no DIO
    assert _by(compute_working_capital_cycle(r), "cash_conversion_cycle") is None
