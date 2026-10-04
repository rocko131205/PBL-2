"""Shock Lab engine tests (deterministic — no LLM needed)."""
from __future__ import annotations

from finveritas.analysis.metrics.debt_service import LoanTerms
from finveritas.analysis.metrics.shock import (
    PRESETS, ShockSpec, credit_view, default_mix, propagate, simulate,
)
from finveritas.shared.schema import FinancialPeriod, NormalizedCompanyRecord


def _saas():
    r = NormalizedCompanyRecord(entity_id="DemoSaaS", source="test", currency="INR",
                                country="IN", industry="Software", saas_subtype="CRM")
    for k, (prev, last) in dict(
        revenue=(800, 1000), cost_of_revenue=(200, 250), gross_profit=(600, 750),
        ebitda=(120, 180), operating_income=(90, 140), net_income=(60, 100),
        operating_cash_flow=(110, 170), capital_expenditure=(20, 30), interest_expense=(10, 12),
        total_debt=(150, 200), equity=(500, 600), current_assets=(400, 450),
        current_liabilities=(250, 300), cash_and_equivalents=(100, 120),
    ).items():
        setattr(r, k, [FinancialPeriod(period="2024-FY", value=prev), FinancialPeriod(period="2025-FY", value=last)])
    return r


TERMS = LoanTerms(principal=300, annual_rate_pct=10, tenure_years=5)


def test_shock_spreads_to_linked_sectors():
    stress = propagate({"US.finance": -15})
    assert stress["US.finance"] >= 15          # direct hit, plus feedback
    assert stress["IN.tech"] > 0               # Indian IT sells to US banks
    assert stress["IN.energy"] == 0            # unrelated node untouched


def test_llm_drafted_spec_is_clamped_and_filtered():
    s = ShockSpec(demand={"EU.finance": -500, "MARS.mining": -10}, rate_bps=9999, start_round=99)
    assert s.demand == {"EU.finance": -60}
    assert s.rate_bps == 600 and s.start_round == 4


def test_no_shock_changes_nothing():
    r = _saas()
    sim = simulate(r, default_mix("IN"), [])
    assert sim.revenue_delta == 0 and sim.ebitda_delta == 0
    assert sim.stressed_record.latest_value("operating_cash_flow") == r.latest_value("operating_cash_flow")


def test_shock_hurts_credit_and_rules_are_repeatable():
    r = _saas()
    shocks = [PRESETS["Western banking stress"]]
    a, b = simulate(r, default_mix("IN"), shocks), simulate(r, default_mix("IN"), shocks)
    assert a.revenue_delta == b.revenue_delta < 0
    base = credit_view("base", r, r.industry, TERMS)
    hit = credit_view("hit", a.stressed_record, r.industry, TERMS, rate_bps=a.rate_bps)
    assert hit.min_dscr < base.min_dscr
    assert r.latest_value("revenue") == 1000   # original record untouched


def test_cloud_cost_spike_hits_ebitda_by_cost_share():
    sim = simulate(_saas(), default_mix("IN"), [PRESETS["Cloud cost spike (cost of revenue +25%)"]])
    assert sim.revenue_delta == 0
    assert abs(sim.ebitda_delta - (-0.25 * 250)) < 0.01


def test_off_menu_ai_pick_falls_back_to_rules():
    def bad_policy(agent, obs):
        return "LAUNCH_ROCKET", "nonsense"
    sim = simulate(_saas(), default_mix("IN"), [PRESETS["Eurozone recession"]], policy=bad_policy)
    assert sim.ai_decisions == 0
    assert all(d["by"] == "rules" for r in sim.rounds for d in r["decisions"].values())
