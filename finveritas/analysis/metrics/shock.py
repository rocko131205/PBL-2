"""Shock Lab engine (V3) — scenario stress testing for SaaS borrowers.

The idea comes from swarm-simulation tools such as MiroFish: build a small world around
the borrower, let its agents react to a shock quarter by quarter, then read the outcome.
Here the world is the borrower's customer base (region.sector segments), its management
and a competitor, and the outcome is a stressed DSCR and credit grade.

Who decides what:
  - Python owns every number: how a shock spreads between industries and countries, what
    each action does to ARR and costs, the stressed financials, DSCR and the grade.
  - Each agent only picks ONE action from a fixed menu per quarter. The default
    `rule_policy` is deterministic and gives the OFFICIAL result. An LLM policy
    (analysis/shock_agents.py) can be plugged in instead; that run is exploratory.

The stressed financials feed the EXISTING engines unchanged: compute_dscr_schedule and
compute_scorecard simply run on a stressed copy of the record.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from pydantic import BaseModel, Field, model_validator

from finveritas.analysis.metrics.debt_service import LoanTerms, compute_dscr_schedule
from finveritas.analysis.metrics.scorecard import compute_scorecard
from finveritas.shared.schema import NormalizedCompanyRecord

ROUNDS = 4  # quarters = one stressed year, which maps onto the annual DSCR numerator


# -------------------------------------------------------------------------
# The economy: region.sector nodes and how stress spreads between them
# -------------------------------------------------------------------------

REGIONS = ("US", "EU", "IN")
SECTORS = ("tech", "finance", "manufacturing", "retail", "energy")
NODES = [f"{r}.{s}" for r in REGIONS for s in SECTORS]

# Share of a stress at the source that reaches the target, before damping.
# ponytail: hand-set weights; swap in OECD ICIO input-output shares for real calibration.
_CROSS_REGION = {("US", "EU"): 0.30, ("US", "IN"): 0.25, ("EU", "IN"): 0.20,
                 ("EU", "US"): 0.15, ("IN", "US"): 0.05, ("IN", "EU"): 0.05}
_WITHIN_REGION = {("energy", "manufacturing"): 0.40, ("manufacturing", "retail"): 0.20,
                  ("manufacturing", "finance"): 0.20, ("retail", "finance"): 0.20,
                  ("finance", "tech"): 0.30, ("manufacturing", "tech"): 0.20,
                  ("retail", "tech"): 0.15}
_DIRECT = {("US.finance", "IN.tech"): 0.30, ("EU.finance", "IN.tech"): 0.25}  # Indian IT sells to Western banks
DAMPING = 0.5


def link_matrix() -> np.ndarray:
    """W[target, source] = how much of the source's stress reaches the target."""
    idx = {n: i for i, n in enumerate(NODES)}
    W = np.zeros((len(NODES), len(NODES)))
    for (src, dst), w in _CROSS_REGION.items():
        for s in SECTORS:
            W[idx[f"{dst}.{s}"], idx[f"{src}.{s}"]] = w
    for r in REGIONS:
        for (src, dst), w in _WITHIN_REGION.items():
            W[idx[f"{r}.{dst}"], idx[f"{r}.{src}"]] = w
    for (src, dst), w in _DIRECT.items():
        W[idx[dst], idx[src]] = w
    return W


def propagate(demand: Dict[str, float]) -> Dict[str, float]:
    """Spread a demand shock through the economy.

    demand: node -> % change in demand/activity, e.g. {"EU.finance": -10}.
    Returns node -> stress = % of demand lost after knock-on effects (positive = worse).
    Solves x = s + d·W·x, i.e. x = (I − d·W)⁻¹ s.
    """
    s = np.array([-demand.get(n, 0.0) for n in NODES])
    x = np.linalg.solve(np.eye(len(NODES)) - DAMPING * link_matrix(), s)
    return {n: round(float(v), 2) for n, v in zip(NODES, x)}


# -------------------------------------------------------------------------
# Shocks
# -------------------------------------------------------------------------

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


class ShockSpec(BaseModel):
    """One shock. Values are clamped and unknown nodes dropped, so LLM-drafted specs are safe."""
    name: str = "Custom shock"
    demand: Dict[str, float] = Field(default_factory=dict, description="node -> % change in demand")
    price_pressure: float = Field(0.0, description="Extra stress on every customer segment (competition, AI disruption)")
    cloud_cost_pct: float = Field(0.0, description="% rise in cost of revenue (hosting / cloud bills)")
    rate_bps: float = Field(0.0, description="Rise in the loan's interest rate, basis points")
    start_round: int = Field(1, description="Quarter the shock hits (>1 = injected mid-simulation)")

    @model_validator(mode="after")
    def _within_limits(self) -> "ShockSpec":
        self.demand = {n: _clamp(v, -60, 60) for n, v in self.demand.items() if n in NODES}
        self.price_pressure = _clamp(self.price_pressure, -20, 30)
        self.cloud_cost_pct = _clamp(self.cloud_cost_pct, -50, 100)
        self.rate_bps = _clamp(self.rate_bps, -300, 600)
        self.start_round = int(_clamp(self.start_round, 1, ROUNDS))
        return self


PRESETS: Dict[str, ShockSpec] = {p.name: p for p in [
    ShockSpec(name="Eurozone recession", demand={"EU.manufacturing": -15, "EU.retail": -10, "EU.finance": -8}),
    ShockSpec(name="US tech budget freeze", demand={"US.tech": -20, "US.finance": -8}),
    ShockSpec(name="Western banking stress", demand={"US.finance": -15, "EU.finance": -12}),
    ShockSpec(name="Energy crisis", demand={"EU.energy": -25, "IN.energy": -15}),
    ShockSpec(name="Global rate shock (+200 bps)", rate_bps=200,
              demand={"US.finance": -5, "EU.finance": -5, "IN.finance": -5}),
    ShockSpec(name="Cloud cost spike (cost of revenue +25%)", cloud_cost_pct=25),
    ShockSpec(name="AI-native competitor price war", price_pressure=8),
]}


def default_mix(country: Optional[str]) -> Dict[str, float]:
    """Starting guess for where the borrower's ARR comes from (% by segment). Editable in the UI."""
    if (country or "").upper() == "IN":
        return {"US.tech": 25, "US.finance": 20, "EU.finance": 15, "IN.tech": 15, "IN.finance": 15, "IN.retail": 10}
    return {"US.tech": 30, "US.finance": 25, "US.retail": 10, "EU.finance": 15, "EU.manufacturing": 10, "IN.tech": 10}


# -------------------------------------------------------------------------
# Agents and their action menus
# -------------------------------------------------------------------------

@dataclass
class Agent:
    id: str
    kind: str                       # customer | management | competitor
    persona: str
    node: Optional[str] = None      # customers only
    share: float = 0.0              # % of ARR at the start (customers only)
    memory: List[str] = field(default_factory=list)


# What each action does in the quarter it is taken. These are the model's assumptions,
# shown in the UI:  arr = % change in that segment's ARR,  arr_all = % change in every
# segment's ARR,  opex = % change in quarterly operating costs,  stress_next = stress added
# to every customer segment next quarter.
ACTIONS: Dict[str, Dict[str, Dict[str, float]]] = {
    "customer": {
        "EXPAND": {"arr": 3.0},
        "RENEW": {},
        "ASK_DISCOUNT": {"arr": -2.0},
        "CUT_SEATS": {"arr": -5.0},
        "PARTIAL_CHURN": {"arr": -12.0},
    },
    "management": {
        "HOLD_COURSE": {},
        "HIRING_FREEZE": {"opex": -3.0},
        "COST_CUTS": {"opex": -7.0, "stress_next": 2.0},
        "RAISE_PRICES": {"arr_all": 2.0, "stress_next": 3.0},
        "RETENTION_DISCOUNTS": {"arr_all": -2.0, "stress_next": -4.0},
    },
    "competitor": {
        "HOLD_PRICES": {},
        "PRICE_WAR": {"stress_next": 5.0},
    },
}


def build_world(record: NormalizedCompanyRecord, mix: Dict[str, float]) -> List[Agent]:
    """Turn the analysed borrower + its customer mix into the simulation's agents."""
    product = record.saas_subtype or "software"
    total = sum(v for n, v in mix.items() if n in NODES and v > 0) or 1.0
    agents = []
    for node, v in mix.items():
        if node not in NODES or v <= 0:
            continue
        region, sector = node.split(".")
        share = v / total * 100
        agents.append(Agent(
            id=f"{region} {sector} customers", kind="customer", node=node, share=share,
            persona=(f"The buying committee of {sector} companies in {region} that subscribe to "
                     f"{record.entity_id}'s {product} product ({share:.0f}% of its ARR)."),
        ))
    agents.append(Agent("Management", "management",
                        f"The CFO of {record.entity_id}, a {product} SaaS company, protecting cash flow and loan covenants."))
    agents.append(Agent("Competitor", "competitor",
                        f"A rival {product} vendor trying to win customers from {record.entity_id}."))
    return agents


def _ladder(value: float, steps: List[Tuple[float, str]], last: str) -> str:
    for limit, action in steps:
        if value < limit:
            return action
    return last


def rule_policy(agent: Agent, obs: dict) -> Tuple[str, str]:
    """Deterministic decisions — the official result. Stress = % of demand lost."""
    s = obs["stress"]
    if agent.kind == "customer":
        action = _ladder(s, [(-5, "EXPAND"), (2, "RENEW"), (8, "ASK_DISCOUNT"), (15, "CUT_SEATS")], "PARTIAL_CHURN")
    elif agent.kind == "management":
        action = _ladder(s, [(5, "HOLD_COURSE"), (12, "HIRING_FREEZE")], "COST_CUTS")
    else:
        action = _ladder(s, [(10, "HOLD_PRICES")], "PRICE_WAR")
    return action, f"rule: stress {s:.1f} → {action}"


Policy = Callable[[Agent, dict], Optional[Tuple[str, str]]]


def _decide(policy: Policy, agent: Agent, obs: dict) -> dict:
    """Run a policy and validate its pick; anything off-menu falls back to the rules."""
    if policy is not rule_policy:
        try:
            pick = policy(agent, obs)
        except Exception:
            pick = None
        if pick and pick[0] in ACTIONS[agent.kind]:
            return {"action": pick[0], "reason": str(pick[1])[:200], "by": "AI"}
    action, reason = rule_policy(agent, obs)
    return {"action": action, "reason": reason, "by": "rules"}


# -------------------------------------------------------------------------
# Simulation
# -------------------------------------------------------------------------

@dataclass
class SimResult:
    agents: List[Agent]
    rounds: List[dict]              # per quarter: stress by node and agent, decisions, ARR
    arr_path: List[float]           # stressed ARR at the end of each quarter
    base_arr_path: List[float]      # ARR path with no shock
    revenue_delta: float            # change in annual revenue vs no shock
    ebitda_delta: float
    cloud_cost_delta: float
    opex_delta: float               # negative = savings from management actions
    rate_bps: float
    stressed_record: NormalizedCompanyRecord
    notes: List[str] = field(default_factory=list)

    @property
    def ai_decisions(self) -> int:
        return sum(d["by"] == "AI" for r in self.rounds for d in r["decisions"].values())


def _quarterly_growth(record: NormalizedCompanyRecord) -> float:
    rev = sorted(record.revenue, key=lambda p: p.period)
    if len(rev) < 2 or rev[-2].value <= 0:
        return 0.0
    yoy = _clamp(rev[-1].value / rev[-2].value - 1, -0.10, 0.40)
    return (1 + yoy) ** 0.25 - 1


def _gross_margin(record: NormalizedCompanyRecord, rev: float, notes: List[str]) -> float:
    gp, cogs = record.latest_value("gross_profit"), record.latest_value("cost_of_revenue")
    if gp is not None:
        return _clamp(gp / rev, 0.0, 1.0)
    if cogs is not None:
        return _clamp(1 - abs(cogs) / rev, 0.0, 1.0)
    notes.append("No gross-margin data — assumed 75%, typical for SaaS.")
    return 0.75


def _cash_opex(record: NormalizedCompanyRecord, rev: float, gm: float, notes: List[str]) -> Optional[float]:
    """Annual operating costs excluding cost of revenue and D&A (gross profit − EBITDA)."""
    ebitda = record.latest_value("ebitda")
    if ebitda is None:
        oi, dep = record.latest_value("operating_income"), record.latest_value("depreciation")
        ebitda = oi + abs(dep) if (oi is not None and dep is not None) else oi
    if ebitda is None:
        notes.append("No EBITDA or operating income — management cost cuts are not counted.")
        return None
    return max(rev * gm - ebitda, 0.0)


def _tax_rate(record: NormalizedCompanyRecord) -> float:
    tax, pre = record.latest_value("income_tax"), record.latest_value("pretax_income")
    if tax is not None and pre and pre > 0:
        return _clamp(abs(tax) / pre, 0.0, 0.35)
    return 0.25


def stress_record(record: NormalizedCompanyRecord, revenue_delta: float, cogs_delta: float,
                  ebitda_delta: float, tax: float) -> NormalizedCompanyRecord:
    """Copy the record and shift its LATEST period by the shock's annual impact."""
    after_tax = ebitda_delta * (1 - tax)
    deltas = {
        "revenue": revenue_delta, "cost_of_revenue": cogs_delta, "gross_profit": revenue_delta - cogs_delta,
        "ebitda": ebitda_delta, "operating_income": ebitda_delta, "net_operating_income": ebitda_delta,
        "pretax_income": ebitda_delta, "net_income": after_tax,
        "operating_cash_flow": after_tax, "free_cash_flow": after_tax,
    }
    out = record.model_copy(deep=True)
    for name, d in deltas.items():
        series = getattr(out, name)
        if not series:
            continue
        latest = max(series, key=lambda p: p.period)
        if name == "cost_of_revenue" and latest.value < 0:  # some sources store costs as negatives
            d = -d
        latest.value += d
    return out


def simulate(record: NormalizedCompanyRecord, mix: Dict[str, float], shocks: List[ShockSpec],
             policy: Policy = rule_policy) -> SimResult:
    """Run the world for ROUNDS quarters and return the stressed financials.

    Every quarter: active shocks spread through the economy → each agent sees its stress
    and picks an action → Python applies the actions' effects to ARR and costs.
    """
    rev = record.latest_value("revenue")
    if not rev or rev <= 0:
        raise ValueError("Shock Lab needs the borrower's latest revenue.")

    notes: List[str] = []
    agents = build_world(record, mix)
    customers = [a for a in agents if a.kind == "customer"]
    if not customers:
        raise ValueError("Add at least one customer segment with a positive ARR share.")
    others = [a for a in agents if a.kind != "customer"]

    g = _quarterly_growth(record)
    gm = _gross_margin(record, rev, notes)
    opex = _cash_opex(record, rev, gm, notes)
    arr = {a.id: rev * a.share / 100 for a in customers}  # ponytail: latest annual revenue stands in for ARR
    base_arr, carry, cloud, opex_delta = rev, 0.0, 0.0, 0.0
    rounds, arr_path, base_path = [], [], []

    for t in range(1, ROUNDS + 1):
        active = [s for s in shocks if s.start_round <= t]
        demand: Dict[str, float] = {}
        for s in active:
            for n, v in s.demand.items():
                demand[n] = demand.get(n, 0.0) + v
        stress = propagate(demand)
        pressure = sum(s.price_pressure for s in active) + carry
        seg = {a.id: stress[a.node] + pressure for a in customers}
        total = sum(arr.values())
        avg = sum(seg[i] * arr[i] for i in arr) / total if total > 0 else 0.0
        obs = {a.id: {"round": t, "stress": seg.get(a.id, avg), "shocks": [s.name for s in active]} for a in agents}

        # Everyone decides at once, on the same start-of-quarter picture.
        with ThreadPoolExecutor(max_workers=8) as ex:
            picks = list(ex.map(lambda a: _decide(policy, a, obs[a.id]), agents))
        decisions = {a.id: p for a, p in zip(agents, picks)}
        effects = {a.id: ACTIONS[a.kind][decisions[a.id]["action"]] for a in agents}

        arr_all = sum(effects[a.id].get("arr_all", 0.0) for a in others)
        for a in customers:
            arr[a.id] *= 1 + g + (effects[a.id].get("arr", 0.0) + arr_all) / 100
        carry = sum(effects[a.id].get("stress_next", 0.0) for a in others)
        if opex is not None:
            opex_delta += opex / 4 * sum(effects[a.id].get("opex", 0.0) for a in others) / 100
        cloud += rev * (1 - gm) / 4 * sum(s.cloud_cost_pct for s in active) / 100
        base_arr *= 1 + g

        arr_path.append(sum(arr.values()))
        base_path.append(base_arr)
        for a in agents:
            d = decisions[a.id]
            a.memory.append(f"Q{t}: stress {obs[a.id]['stress']:.1f}% demand lost; I chose {d['action']} — {d['reason']}")
        rounds.append({"round": t, "shocks": obs[agents[0].id]["shocks"], "pressure": round(pressure, 2),
                       "stress": {n: v for n, v in stress.items() if abs(v) > 0.05},
                       "agent_stress": {a.id: round(obs[a.id]["stress"], 2) for a in agents},
                       "decisions": decisions, "arr": sum(arr.values())})

    revenue_delta = round(sum(a - b for a, b in zip(arr_path, base_path)) / 4, 2)  # 4 quarters of ARR/4
    cogs_delta = revenue_delta * (1 - gm) + cloud
    ebitda_delta = round(revenue_delta - cogs_delta - opex_delta, 2)
    rate_bps = sum(s.rate_bps for s in shocks)
    return SimResult(
        agents=agents, rounds=rounds, arr_path=arr_path, base_arr_path=base_path,
        revenue_delta=revenue_delta, ebitda_delta=ebitda_delta, cloud_cost_delta=round(cloud, 2),
        opex_delta=round(opex_delta, 2), rate_bps=rate_bps,
        stressed_record=stress_record(record, revenue_delta, cogs_delta, ebitda_delta, _tax_rate(record)),
        notes=notes,
    )


# -------------------------------------------------------------------------
# Credit impact (existing engines, unchanged)
# -------------------------------------------------------------------------

class CreditView(BaseModel):
    label: str
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    min_dscr: Optional[float] = None
    breaches_1x: bool = False
    grade: str = "NR"
    grade_label: str = "Not Rated"
    pd_band: str = "n/a"
    composite: Optional[float] = None


def credit_view(label: str, record: NormalizedCompanyRecord, industry: Optional[str],
                terms: Optional[LoanTerms] = None, basis: str = "cfads", rate_bps: float = 0.0) -> CreditView:
    """DSCR + grade for a (possibly stressed) record, via the existing engines."""
    min_dscr = None
    if terms is not None:
        shocked = terms.model_copy(update={"annual_rate_pct": max(0.0, terms.annual_rate_pct + rate_bps / 100)})
        min_dscr = compute_dscr_schedule(record, shocked, basis=basis, run_stress=False).min_dscr
    sc = compute_scorecard(record, industry=industry, min_dscr=min_dscr)
    return CreditView(
        label=label, revenue=record.latest_value("revenue"), ebitda=record.latest_value("ebitda"),
        min_dscr=min_dscr, breaches_1x=min_dscr is not None and min_dscr < 1.0,
        grade=sc.grade, grade_label=sc.grade_label, pd_band=sc.pd_band, composite=sc.composite_score,
    )
