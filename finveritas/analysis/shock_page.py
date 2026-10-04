"""Shock Lab page (V3) — scenario simulation for SaaS borrowers, inspired by MiroFish.

Flow: 1 Scenario → 2 World → 3 Simulate → 4 Credit impact → 5 Agent timeline → 6 Report & interviews.
Every number comes from analysis/metrics/shock.py and the existing DSCR/scorecard engines.
The AI only drafts custom scenarios, plays the agents in the optional exploratory run,
writes the note and answers interviews.
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from finveritas.analysis.metrics.debt_service import LoanTerms
from finveritas.analysis.metrics.shock import (
    ACTIONS, NODES, PRESETS, ROUNDS, CreditView, ShockSpec, SimResult,
    credit_view, default_mix, link_matrix, simulate,
)
from finveritas.analysis.shock_agents import interpret_scenario, interview, make_llm_policy, write_report
from finveritas.shared.components import SAAS_ONLY_NOTE, render_hr, render_section_header
from finveritas.shared.formatting import format_money, format_ratio
from finveritas.shared.schema import NormalizedCompanyRecord

_CUSTOM = "Describe your own shock (AI drafts it)…"
_GRADES = ["AA", "A", "BBB", "BB", "B", "CCC", "D", "NR"]


def _spec_line(s: ShockSpec) -> str:
    parts = [f"{n} {v:+.0f}% demand" for n, v in s.demand.items()]
    if s.price_pressure:
        parts.append(f"price pressure {s.price_pressure:+.0f}")
    if s.cloud_cost_pct:
        parts.append(f"cost of revenue {s.cloud_cost_pct:+.0f}%")
    if s.rate_bps:
        parts.append(f"interest rate {s.rate_bps:+.0f} bps")
    return f"**{s.name}** (from Q{s.start_round}): " + (" · ".join(parts) or "no effect")


def _effect_text(effect: dict) -> str:
    labels = {"arr": "segment ARR", "arr_all": "all ARR", "opex": "operating costs", "stress_next": "customer stress next quarter"}
    return ", ".join(f"{labels[k]} {v:+g}{'' if k == 'stress_next' else '%'}" for k, v in effect.items()) or "no change"


def _heat(stress: float) -> str:
    if stress < -0.05:
        return "#34D399"
    for limit, color in ((10, "#FF4D4D"), (4, "#FF9F43"), (0.05, "#FFD166")):
        if stress >= limit:
            return color
    return "#2E3A59"


def _contagion_graph(sim: SimResult, entity: str) -> None:
    stress = sim.rounds[-1]["stress"]
    customers = {a.node for a in sim.agents if a.kind == "customer"}
    shown = sorted(set(stress) | customers)
    W, idx = link_matrix(), {n: i for i, n in enumerate(NODES)}
    nodes = [Node(id=n, label=f"{n}\n{stress.get(n, 0):.1f}%", color=_heat(stress.get(n, 0)), shape="dot",
                  size=12 + min(abs(stress.get(n, 0)), 30), font={"color": "#CCCCCC", "size": 12}) for n in shown]
    nodes.append(Node(id="__borrower", label=entity, color="#FFB000", shape="star", size=30,
                      font={"color": "#FFB000", "size": 14}))
    edges = [Edge(source=s, target=t, color="#555566", width=1)
             for t in shown for s in shown if W[idx[t], idx[s]] > 0 and abs(stress.get(s, 0)) > 0.05]
    edges += [Edge(source=n, target="__borrower", color="#FFB000", width=2) for n in customers]
    agraph(nodes=nodes, edges=edges, config=Config(width="100%", height=420, directed=True, physics=True))


def _facts(record: NormalizedCompanyRecord, shocks: List[ShockSpec], sim: SimResult, views: List[CreditView]) -> List[str]:
    """Deterministic fact lines that ground the AI report."""
    ccy = record.currency
    lines = [
        f"Borrower: {record.entity_id} ({record.industry or 'SaaS'})",
        "Shocks: " + "; ".join(f"{s.name} from Q{s.start_round}" for s in shocks),
        f"Change in annual revenue vs no shock: {format_money(sim.revenue_delta, ccy)}",
        f"Change in annual EBITDA vs no shock: {format_money(sim.ebitda_delta, ccy)}",
        f"Extra cloud/hosting cost: {format_money(sim.cloud_cost_delta, ccy)}",
        f"Management cost savings: {format_money(-sim.opex_delta, ccy)}",
        f"Loan rate change: {sim.rate_bps:+.0f} bps",
    ]
    for r in sim.rounds:
        lines.append(f"Q{r['round']} decisions: " + "; ".join(f"{a} → {d['action']}" for a, d in r["decisions"].items()))
    for v in views:
        lines.append(f"{v.label}: min DSCR {format_ratio(v.min_dscr)}, grade {v.grade} ({v.grade_label}), PD band {v.pd_band}")
    return lines


def _loan_terms(ccy: Optional[str]) -> tuple[Optional[LoanTerms], str]:
    """Reuse the loan entered in Financial Analysis → Debt Serviceability."""
    t = st.session_state.get("v3_dscr_terms") or {}
    if t.get("principal", 0) <= 0:
        st.info("No loan entered yet, so the grade is shown without DSCR. Enter loan terms in "
                "**Financial Analysis → Debt Serviceability** to see DSCR under stress.")
        return None, "cfads"
    terms = LoanTerms(**{k: v for k, v in t.items() if k != "basis"})
    st.caption(f"Loan under test: {format_money(terms.principal, ccy)} at {terms.annual_rate_pct:g}% "
               f"for {terms.tenure_years} years (from Debt Serviceability).")
    return terms, t.get("basis", "cfads")


def page_shock_lab() -> None:
    render_section_header("Shock Lab", subtitle="Simulate an economic shock and watch it reach this SaaS borrower's credit")

    workflow_state = (st.session_state.get("agent_outputs") or {}).get("workflow_state", {})
    record_data = workflow_state.get("company_record")
    if not record_data:
        st.warning("⚠️ Run an analysis first (**Upload Statement → RUN FULL ANALYSIS**). Shock Lab stresses that borrower.")
        return
    record = NormalizedCompanyRecord(**record_data)
    profile = workflow_state.get("company_profile") or {}
    industry = record.industry or profile.get("industry")
    ccy = record.currency
    if profile.get("is_saas") is not True:
        st.warning(f"⚠️ This borrower was not classified as a SaaS company. {SAAS_ONLY_NOTE}")
    if not record.latest_value("revenue"):
        st.error("This borrower has no revenue figure, which Shock Lab needs.")
        return

    st.markdown(
        '<p style="font-size:12px;color:#7A7D96;line-height:1.6;">'
        "Pick a shock. It spreads through industries and countries, reaches the borrower's customer "
        f"segments, and each agent (customers, management, a competitor) reacts every quarter for {ROUNDS} "
        "quarters. <b>Python computes every number</b>; the official result uses fixed decision rules. "
        "You can also let AI agents decide, as a clearly-labelled exploratory run.</p>",
        unsafe_allow_html=True,
    )

    # ── 1. Scenario ───────────────────────────────────────────────────────
    render_section_header("1 · Scenario", subtitle="A preset, or describe your own")
    choice = st.selectbox("Shock", list(PRESETS) + [_CUSTOM], key="shock_choice")
    main = PRESETS.get(choice)
    if choice == _CUSTOM:
        text = st.text_area("Describe the shock", key="shock_text",
                            placeholder="e.g. A US banking crisis makes banks freeze software budgets for a year")
        if st.button("Draft scenario with AI"):
            with st.spinner("Reading your scenario…"):
                st.session_state["shock_custom"] = interpret_scenario(text)
            if st.session_state["shock_custom"] is None:
                st.error("Couldn't turn that into a scenario. Try rephrasing, or pick a preset.")
        main = st.session_state.get("shock_custom")
        if main:
            st.caption("AI-drafted assumptions. Check them before running:")
    if main:
        st.markdown(_spec_line(main))

    with st.expander("God's-eye view: inject a second event mid-simulation (optional)"):
        inject = st.selectbox("Event", ["None"] + list(PRESETS), key="shock_inject")
        inject_q = st.slider("Hits in quarter", 2, ROUNDS, 3, key="shock_inject_q")
    shocks = [main] if main else []
    if inject != "None":
        shocks.append(PRESETS[inject].model_copy(update={"start_round": inject_q}))
        st.markdown(_spec_line(shocks[-1]))

    # ── 2. World ──────────────────────────────────────────────────────────
    render_hr()
    render_section_header("2 · The world", subtitle="Where the borrower's recurring revenue comes from")
    st.caption("Each row becomes a customer agent. Shares are rescaled to 100%. "
               "Management (the CFO) and a competitor join as agents too.")
    edited = st.data_editor(
        pd.DataFrame([{"Segment": n, "ARR share %": v} for n, v in default_mix(record.country).items()]),
        num_rows="dynamic", hide_index=True, key=f"shock_mix_{record.entity_id}",
        column_config={
            "Segment": st.column_config.SelectboxColumn(options=NODES, required=True),
            "ARR share %": st.column_config.NumberColumn(min_value=0, max_value=100, step=5),
        },
    )
    mix: dict = {}
    for row in edited.to_dict("records"):
        seg, share = row.get("Segment"), row.get("ARR share %") or 0
        if seg in NODES and share > 0:
            mix[seg] = mix.get(seg, 0.0) + float(share)
    terms, basis = _loan_terms(ccy)

    # ── 3. Simulate ───────────────────────────────────────────────────────
    render_hr()
    render_section_header("3 · Simulate", subtitle=f"{ROUNDS} quarters, every agent decides each quarter")
    use_ai = st.toggle("Also let AI agents decide (exploratory, uses the LLM)", key="shock_use_ai")
    if st.button("Run simulation", type="primary", width="stretch", disabled=not (shocks and mix)):
        try:
            official = simulate(record, mix, shocks)
            ai = None
            if use_ai:
                with st.spinner(f"AI agents are deciding, quarter by quarter ({ROUNDS} quarters)…"):
                    ai = simulate(record, mix, shocks, policy=make_llm_policy("; ".join(s.name for s in shocks)))
        except ValueError as exc:
            st.error(str(exc))
            return
        st.session_state["shock_lab"] = {"entity": record.entity_id, "shocks": shocks, "official": official,
                                         "ai": ai, "report": None, "answer": None}

    run = st.session_state.get("shock_lab")
    if not run or run["entity"] != record.entity_id:
        return
    official, ai = run["official"], run["ai"]

    # ── 4. Credit impact ──────────────────────────────────────────────────
    render_hr()
    render_section_header("4 · Credit impact", subtitle="Existing DSCR + scorecard engines, run on the stressed financials")
    views = [credit_view("Base case", record, industry, terms, basis),
             credit_view("Shock · rules (official)", official.stressed_record, industry, terms, basis, official.rate_bps)]
    if ai:
        views.append(credit_view("Shock · AI agents (exploratory)", ai.stressed_record, industry, terms, basis, ai.rate_bps))
    st.dataframe(pd.DataFrame({v.label: {
        "Revenue": format_money(v.revenue, ccy), "EBITDA": format_money(v.ebitda, ccy),
        "Min DSCR": format_ratio(v.min_dscr), "Grade": f"{v.grade} · {v.grade_label}", "PD band": v.pd_band,
    } for v in views}), width="stretch")
    base_v, off_v = views[0], views[1]
    if off_v.breaches_1x:
        st.error("Under this shock the minimum DSCR falls below 1.0×: the borrower could not cover its debt service.")
    elif _GRADES.index(off_v.grade) > _GRADES.index(base_v.grade):
        st.warning(f"Rating migration: {base_v.grade} → {off_v.grade} (PD band {base_v.pd_band} → {off_v.pd_band}).")
    else:
        st.success(f"Grade holds at {off_v.grade} under this shock.")
    for note in official.notes:
        st.caption(note)

    quarters = [f"Q{r['round']}" for r in official.rounds]
    arr = {"No shock": official.base_arr_path, "Shock · rules": official.arr_path}
    if ai:
        arr["Shock · AI agents"] = ai.arr_path
    st.caption("Annual recurring revenue at the end of each quarter")
    st.line_chart(pd.DataFrame(arr, index=quarters))

    st.caption("How the shock spread (final quarter, % of demand lost; gold edges = the borrower's customers)")
    _contagion_graph(official, record.entity_id)

    # ── 5. Agent timeline ─────────────────────────────────────────────────
    render_hr()
    render_section_header("5 · What each agent did", subtitle="Every decision, every quarter")
    sims = [("Rules (official)", official)] + ([("AI agents (exploratory)", ai)] if ai else [])
    for tab, (_, sim) in zip(st.tabs([name for name, _ in sims]), sims):
        with tab:
            st.dataframe(pd.DataFrame([
                {"Quarter": f"Q{r['round']}", "Agent": a, "Stress": r["agent_stress"][a], "Action": d["action"],
                 "Why": d["reason"], "Decided by": d["by"]}
                for r in sim.rounds for a, d in r["decisions"].items()
            ]), hide_index=True, width="stretch")
    if ai:
        total = sum(len(r["decisions"]) for r in ai.rounds)
        st.caption(f"{ai.ai_decisions} of {total} decisions came from the LLM; the rest fell back to the rules.")
    with st.expander("Model assumptions (what each action does)"):
        st.dataframe(pd.DataFrame([{"Agent": kind, "Action": a, "Effect that quarter": _effect_text(e)}
                                   for kind, acts in ACTIONS.items() for a, e in acts.items()]),
                     hide_index=True, width="stretch")
        st.caption("Stress spreads between industries and countries with hand-set link weights (damping 0.5). "
                   "Revenue lost costs EBITDA at the gross margin; cost of revenue scales with revenue. "
                   "The stressed year's change is applied to the latest reported year.")

    # ── 6. Report & interviews ────────────────────────────────────────────
    render_hr()
    render_section_header("6 · Report & interviews", subtitle="AI explains the computed results, never changes them")
    if st.button("Write stress-test note (AI)"):
        with st.spinner("Writing the note…"):
            run["report"] = write_report(_facts(record, run["shocks"], official, views))
    if run["report"]:
        st.markdown(run["report"])

    agents = (ai or official).agents
    who = st.selectbox("Interview an agent", [a.id for a in agents], key="shock_interviewee")
    question = st.text_input("Question", key="shock_question", placeholder="Why did you cut seats in Q2?")
    if st.button("Ask"):
        with st.spinner("Asking…"):
            run["answer"] = (who, interview(next(a for a in agents if a.id == who), question))
    if run["answer"]:
        st.markdown(f"**{run['answer'][0]}:** {run['answer'][1]}")
