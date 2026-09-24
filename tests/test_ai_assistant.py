"""V3 Phase 7 — AI assistant grounding tests (no live LLM calls)."""
from __future__ import annotations

from finveritas.analysis.assistant import build_fact_context, answer_question


def _state():
    return {
        "company_record": {"entity_id": "Acme Corp", "industry": "Software", "currency": "USD"},
        "fact_ledger": {"entries": [
            {"display_name": "Operating Margin", "metric": "operating_margin", "value": 24.5, "unit": "%", "risk_signal": "PASS"},
            {"display_name": "Debt / Equity", "metric": "debt_to_equity", "value": 0.4, "unit": "x"},
            {"display_name": "Missing Metric", "metric": "x", "value": None},
        ]},
        "dscr_result": {"dscr_ratio": 1.85, "risk_level": "MODERATE"},
        "risk_dashboard": {"overall_risk": "MODERATE", "fail_count": 0, "warn_count": 2},
    }


class TestFactContext:
    def test_includes_company_and_metrics(self):
        ctx = build_fact_context(_state())
        assert "Acme Corp" in ctx
        assert "Software" in ctx
        assert "Operating Margin: 24.5%" in ctx
        assert "PASS" in ctx

    def test_includes_dscr_and_risk(self):
        ctx = build_fact_context(_state())
        assert "DSCR: 1.85x" in ctx
        assert "Overall risk: MODERATE" in ctx

    def test_skips_none_values(self):
        ctx = build_fact_context(_state())
        assert "Missing Metric" not in ctx

    def test_extra_lines_appended(self):
        ctx = build_fact_context(_state(), extra_lines=["Credit grade: BBB (composite 68/100)"])
        assert "Credit grade: BBB" in ctx

    def test_empty_state(self):
        assert "No computed facts" in build_fact_context({})


class TestGuardedQA:
    def test_empty_question_short_circuits(self):
        # No LLM call for an empty question.
        assert "Ask a question" in answer_question("   ", _state())
