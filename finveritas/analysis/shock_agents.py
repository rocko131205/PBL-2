"""Shock Lab AI layer (V3) — gives the simulated agents a voice. Never computes a number.

  - interpret_scenario(): plain-English shock -> ShockSpec. The schema clamps every value
    and drops unknown nodes, and the analyst sees the spec before running it.
  - make_llm_policy(): each agent picks ONE action from its fixed menu, in persona, using
    its memory of earlier quarters. Off-menu or failed picks fall back to the rules.
  - interview(): ask any agent, after the run, why it did what it did.
  - write_report(): narrates the run from the computed facts only.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from finveritas.analysis.assistant import _GUARDRAIL, _call
from finveritas.analysis.metrics.shock import ACTIONS, NODES, Agent, ShockSpec
from finveritas.analysis.workflow import _extract_json


def interpret_scenario(text: str) -> Optional[ShockSpec]:
    """Turn a described shock into a ShockSpec, or None if the LLM can't produce a usable one."""
    if not text or not text.strip():
        return None
    system = (
        "You convert a described economic shock into JSON for a credit stress-testing engine. "
        "Return ONLY a JSON object with keys: name (short title), demand (object mapping node -> % "
        "change in demand, negative = fall, between -60 and 60), price_pressure (0-30, extra "
        "competitive pressure on a SaaS vendor's customers), cloud_cost_pct (% rise in hosting / cloud "
        "costs), rate_bps (rise in interest rates, basis points). "
        f"Use ONLY these demand nodes: {', '.join(NODES)}. Leave out anything the text doesn't imply."
    )
    data = _extract_json(_call(system, text.strip(), timeout=30))
    if not isinstance(data, dict):
        return None
    try:
        spec = ShockSpec(**{k: v for k, v in data.items() if k in ShockSpec.model_fields and k != "start_round"})
    except Exception:
        return None
    if not (spec.demand or spec.price_pressure or spec.cloud_cost_pct or spec.rate_bps):
        return None
    return spec


def make_llm_policy(scenario: str):
    """An LLM-backed policy for simulate(). Stops calling the LLM after repeated failures,
    so a down endpoint costs a few seconds, not the whole run."""
    failures = [0]

    def policy(agent: Agent, obs: dict) -> Optional[Tuple[str, str]]:
        if failures[0] >= 3:
            return None
        user = (
            f"You are: {agent.persona}\n"
            f"Scenario: {scenario}\n"
            f"It is quarter Q{obs['round']}. Shocks in effect: {', '.join(obs['shocks']) or 'none'}.\n"
            f"Stress you face: {obs['stress']:.1f} (≈ % of demand lost; 0 = normal, 15+ = severe).\n"
            "Your earlier quarters:\n" + ("\n".join(agent.memory[-3:]) or "none yet") + "\n\n"
            f"Choose exactly ONE action from: {', '.join(ACTIONS[agent.kind])}.\n"
            'Reply ONLY with JSON: {"action": "<ACTION>", "reason": "<max 20 words>"}'
        )
        data = _extract_json(_call(
            "You role-play one participant in an economic simulation. Stay in character and be realistic.",
            user, timeout=20,
        ))
        if not isinstance(data, dict) or data.get("action") not in ACTIONS[agent.kind]:
            failures[0] += 1
            return None
        failures[0] = 0
        return data["action"], str(data.get("reason", ""))

    return policy


def interview(agent: Agent, question: str) -> str:
    """Ask a simulated agent about its decisions (answers from its own memory only)."""
    if not question or not question.strip():
        return "Ask the agent a question."
    system = (
        f"You are {agent.persona} You just lived through a simulated economic shock, one quarter "
        "at a time. Answer in character in 2-4 sentences. Only mention numbers that appear in your "
        "memory below; never invent figures."
    )
    user = "Your memory of the simulation:\n" + "\n".join(agent.memory) + f"\n\nInterviewer: {question.strip()}"
    return _call(system, user, timeout=30)


def write_report(facts: List[str]) -> str:
    """Short credit-committee note on the stress test, grounded in the computed facts."""
    user = (
        "Write a short stress-test note for a credit committee (4-6 sentences): what the shock was, "
        "how it reached this borrower, how customers and management reacted, and what it does to "
        "debt-service coverage and the credit grade.\n\nCOMPUTED FACTS:\n" + "\n".join(facts)
    )
    return _call(_GUARDRAIL, user, timeout=60)
