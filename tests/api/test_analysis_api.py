"""Analysis API: background run + progress, the report, DSCR, assistant, memo, history, isolation.

The real LangGraph pipeline runs; only its two external dependencies are stubbed:
the LLM (offline, so the nodes take their graceful fallback paths) and the peer
lookup (Yahoo Finance).
"""
from __future__ import annotations

import io

import pytest

from api import jobs
from api.routers import analysis as analysis_router
from finveritas.analysis import workflow as wf

from .conftest import STRONG_PASSWORD, csrf, login

CSV = (
    "period,revenue,operating_income,net_income,ebitda,interest_expense,total_assets,total_liabilities,"
    "current_assets,current_liabilities,equity,total_debt\n"
    "2021-FY,900000,120000,80000,160000,20000,1850000,1100000,900000,500000,750000,600000\n"
    "2022-FY,1000000,150000,100000,190000,22000,2000000,1200000,950000,520000,800000,620000\n"
    "2023-FY,1200000,190000,130000,240000,24000,2300000,1350000,1000000,540000,950000,640000\n"
    "2024-FY,1500000,260000,180000,320000,25000,2700000,1500000,1100000,560000,1200000,650000\n"
)
DSCR = {"principal": 500000, "annual_rate_pct": 10, "tenure_years": 5, "structure": "equal_installment",
        "moratorium_years": 0, "existing_annual_debt_service": 0, "basis": "ebitda"}


@pytest.fixture(autouse=True)
def offline_pipeline(monkeypatch):
    def no_llm(*_a, **_k):
        raise RuntimeError("Connection refused by http://10.1.2.3:1234/v1 (LLM offline)")

    def no_peers(state):
        state["peer_comparison"] = {"target_entity": "x", "comparison_metrics": {}, "selection_rationale": "stub", "peers": [
            {"entity_id": "Peer One", "ticker": "P1", "peer_tier": "primary", "revenue_growth": 12.5,
             "operating_margin": 18.0, "gross_margin": 40.0, "debt_to_equity": 0.6},
        ]}
        return state

    monkeypatch.setattr(wf, "_get_llm", no_llm)
    monkeypatch.setattr(wf, "peer_analysis_node", no_peers)
    monkeypatch.setattr(jobs, "_submit", lambda fn, *args: fn(*args))  # run jobs inline
    monkeypatch.setenv("LLM_API_KEY", "sk-super-secret-llm-key")


@pytest.fixture
def ready(client, user):
    """Signed in with a complete CSV loaded."""
    login(client)
    r = client.post("/api/ingest/csv", headers=csrf(client),
                    files={"file": ("acme.csv", io.BytesIO(CSV.encode()), "text/csv")},
                    data={"company_name": "Acme <b>Pvt</b> Ltd", "currency": "INR"})
    assert r.status_code == 200, r.text
    return client


def _run(client) -> dict:
    r = client.post("/api/analysis", headers=csrf(client))
    assert r.status_code == 202, r.text
    return client.get(f"/api/analysis/{r.json()['id']}").json()


# ── Running ─────────────────────────────────────────────────────────────────

def test_run_completes_with_every_stage_reported(ready):
    run = _run(ready)
    assert run["status"] == "done"
    assert [s["status"] for s in run["stages"]] == ["done"] * 5
    assert [s["key"] for s in run["stages"]] == [k for k, _ in wf.PIPELINE_STAGES]
    cur = ready.get("/api/analysis/current").json()
    assert cur["id"] == run["id"] and cur["status"] == "done"


def test_report_has_every_section(ready):
    rep = _run(ready)["report"]
    assert rep["entity"] == "Acme <b>Pvt</b> Ltd" and rep["currency"] == "INR"
    assert rep["verdict"]["grade"] and rep["scorecard"]["factors"]
    assert {s["category"] for s in rep["ledger"]} >= {"profitability", "liquidity", "solvency"}
    row = rep["ledger"][0]["rows"][0]
    assert {"name", "display", "signal", "formula", "meaning"} <= row.keys()
    assert rep["anomalies"]["items"] is not None
    rows = rep["trends"]["revenue"]["rows"]
    assert any(r.get("forecast") for r in rows) and any("history" in r for r in rows)
    assert all(len(r["band"]) == 2 for r in rows if r.get("forecast"))
    assert rep["trends"]["margin"]["trend"] in {"improving", "declining", "flat"}
    assert rep["peers"][0]["entity_id"] == "Peer One"
    assert rep["dscr_bases"] and {b["key"] for b in rep["dscr_bases"]} >= {"ebitda", "ebit"}


def test_risk_counts_come_from_indicators_not_lost_properties(ready):
    risk = _run(ready)["report"]["risk"]
    statuses = [i["status"] for i in risk["indicators"]]
    assert risk["fail_count"] == statuses.count("FAIL") and risk["warn_count"] == statuses.count("WARN")


def test_server_secrets_never_stored_or_returned(ready, mongo):
    run = _run(ready)
    stored = mongo.analyses.find_one({})["result"]
    for key in ("llm_api_key", "llm_base_url", "fmp_api_key", "news_api_key"):
        assert key not in stored
    raw = ready.get(f"/api/analysis/{run['id']}/raw")
    body = ready.get(f"/api/analysis/{run['id']}").text + raw.text
    assert "sk-super-secret-llm-key" not in body
    assert "10.1.2.3" not in body  # internal host from the LLM error message is redacted
    assert run["report"]["errors"]  # the degraded stages are still reported


def test_cannot_start_without_data(client, user):
    login(client)
    assert client.post("/api/analysis", headers=csrf(client)).status_code == 400
    assert client.get("/api/analysis/current").json() == {"status": "none", "has_data": False}


def test_only_one_run_at_a_time(ready, monkeypatch):
    monkeypatch.setattr(jobs, "_submit", lambda fn, *args: None)  # leave it queued
    first = ready.post("/api/analysis", headers=csrf(ready))
    assert first.status_code == 202 and first.json()["status"] == "queued"
    second = ready.post("/api/analysis", headers=csrf(ready))
    assert second.status_code == 409 and second.json()["id"] == first.json()["id"]


def test_runs_are_rate_limited(ready, monkeypatch):
    monkeypatch.setattr(jobs, "RUN_MAX", 2)
    codes = [ready.post("/api/analysis", headers=csrf(ready)).status_code for _ in range(3)]
    assert codes == [202, 202, 429]


def test_failed_run_reports_a_reference_not_internals(ready, monkeypatch):
    def boom(**_):
        raise RuntimeError("pymongo.errors.ServerSelectionTimeoutError: db.internal:27017")
    monkeypatch.setattr(jobs, "run_analysis", boom)
    run = _run(ready)
    assert run["status"] == "failed" and "reference" in run["error"] and "db.internal" not in run["error"]
    assert "report" not in run


def test_interrupted_runs_are_marked_failed_on_startup(ready, mongo, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(jobs, "_submit", lambda fn, *args: None)
    rid = ready.post("/api/analysis", headers=csrf(ready)).json()["id"]
    # A run another live process is executing has a fresh heartbeat and must be left alone...
    assert jobs.recover_interrupted() == 0
    assert ready.get(f"/api/analysis/{rid}").json()["status"] == "queued"
    # ...but once its process has died the heartbeat goes stale and the run is failed.
    mongo.analysis_locks.update_many({}, {"$set": {"heartbeat": datetime.now(timezone.utc) - timedelta(hours=1)}})
    assert jobs.recover_interrupted() == 1
    run = ready.get(f"/api/analysis/{rid}").json()
    assert run["status"] == "failed" and "restarted" in run["error"]


def test_changing_the_data_unlinks_the_old_analysis(ready):
    _run(ready)
    ready.put("/api/workspace/scale", headers=csrf(ready), json={"multiplier": 1e7})
    assert ready.get("/api/analysis/current").json()["status"] == "none"


def test_scale_is_applied_to_the_analysed_data(ready):
    ready.put("/api/workspace/scale", headers=csrf(ready), json={"multiplier": 1e7})
    rows = _run(ready)["report"]["trends"]["revenue"]["rows"]
    assert next(r["history"] for r in rows if r["period"] == "2024-FY") == 1_500_000 * 1e7


# ── History (previously never written) ──────────────────────────────────────

def test_completed_run_appears_in_file_history(ready):
    run = _run(ready)
    rows = ready.get("/api/history").json()
    assert len(rows) == 1
    assert rows[0]["analysis_id"] == run["id"] and rows[0]["source_type"] == "csv"
    assert isinstance(rows[0]["credibility_score"], int) and rows[0]["entity_name"] == "Acme <b>Pvt</b> Ltd"


# ── DSCR ────────────────────────────────────────────────────────────────────

def test_dscr_schedule_and_it_feeds_the_scorecard(ready):
    run = _run(ready)
    r = ready.post(f"/api/analysis/{run['id']}/dscr", headers=csrf(ready), json=DSCR)
    assert r.status_code == 200, r.text
    view = r.json()
    assert view["min_dscr"] > 0 and len(view["schedule"]) == 5 and view["verdict"]["tone"] in {"good", "watch", "risk"}
    assert all("dscr" in row and "payment" not in row and row["total_payment_display"] for row in view["schedule"])
    assert view["stress_results"] and view["method"]
    rep = ready.get(f"/api/analysis/{run['id']}").json()["report"]
    assert rep["verdict"]["min_dscr"] == view["min_dscr"] and rep["dscr"]["min_dscr"] == view["min_dscr"]
    assert rep["dscr_terms"]["principal"] == 500000


@pytest.mark.parametrize("patch", [
    {"principal": 0}, {"principal": -5}, {"annual_rate_pct": 101}, {"tenure_years": 0}, {"tenure_years": 41},
    {"structure": "weird"}, {"basis": "magic"}, {"moratorium_years": 5}, {"existing_annual_debt_service": -1},
])
def test_dscr_rejects_bad_terms(ready, patch):
    run = _run(ready)
    assert ready.post(f"/api/analysis/{run['id']}/dscr", headers=csrf(ready), json={**DSCR, **patch}).status_code == 422


def test_dscr_rejects_a_basis_the_data_cannot_support(ready):
    run = _run(ready)  # this CSV has no operating cash flow
    r = ready.post(f"/api/analysis/{run['id']}/dscr", headers=csrf(ready), json={**DSCR, "basis": "cfads"})
    assert r.status_code == 422


# ── Assistant ───────────────────────────────────────────────────────────────

def test_assistant_explain_and_ask_are_stored(ready, monkeypatch):
    seen = {}
    monkeypatch.setattr(analysis_router, "explain_results", lambda state, extra: "Healthy margins; watch leverage.")

    def fake_answer(q, state, extra):
        seen["extra"] = extra
        return f"Answer to: {q}"
    monkeypatch.setattr(analysis_router, "answer_question", fake_answer)
    run = _run(ready)
    assert ready.post(f"/api/analysis/{run['id']}/assistant/explain", headers=csrf(ready)).json()["text"].startswith("Healthy")
    a = ready.post(f"/api/analysis/{run['id']}/assistant/ask", headers=csrf(ready), json={"question": "Is leverage a concern?"})
    assert a.json()["a"] == "Answer to: Is leverage a concern?"
    assert seen["extra"] and seen["extra"][0].startswith("Credit grade:")  # grounded with the computed grade
    ai = ready.get(f"/api/analysis/{run['id']}").json()["report"]["ai"]
    assert ai["explain"].startswith("Healthy") and ai["qa"][-1]["q"] == "Is leverage a concern?"


def test_assistant_input_validation_and_throttle(ready, monkeypatch):
    monkeypatch.setattr(analysis_router, "answer_question", lambda q, s, e: "ok")
    monkeypatch.setattr(analysis_router, "AI_MAX", 2)
    run = _run(ready)
    url = f"/api/analysis/{run['id']}/assistant/ask"
    assert ready.post(url, headers=csrf(ready), json={"question": ""}).status_code == 422
    assert ready.post(url, headers=csrf(ready), json={"question": "x" * 1001}).status_code == 422
    codes = [ready.post(url, headers=csrf(ready), json={"question": "q"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_qa_history_is_capped(ready, monkeypatch, mongo):
    monkeypatch.setattr(analysis_router, "answer_question", lambda q, s, e: "ok")
    monkeypatch.setattr(analysis_router, "QA_KEEP", 3)
    run = _run(ready)
    for i in range(5):
        ready.post(f"/api/analysis/{run['id']}/assistant/ask", headers=csrf(ready), json={"question": f"q{i}"})
    qa = mongo.analyses.find_one({})["ai"]["qa"]
    assert [x["q"] for x in qa] == ["q2", "q3", "q4"]


# ── Memo ────────────────────────────────────────────────────────────────────

def test_memo_is_escaped_and_locked_down(ready):
    run = _run(ready)
    r = ready.get(f"/api/analysis/{run['id']}/memo")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "<b>Pvt</b>" not in r.text and "&lt;b&gt;Pvt&lt;/b&gt;" in r.text
    d = ready.get(f"/api/analysis/{run['id']}/memo?download=true")
    assert 'attachment; filename="credit_memo_Acme_b_Pvt_b_Ltd.html"' == d.headers["content-disposition"]


# ── Isolation ───────────────────────────────────────────────────────────────

def test_other_users_cannot_touch_my_analysis(ready, client, monkeypatch):
    monkeypatch.setattr(analysis_router, "answer_question", lambda q, s, e: "leak")
    run = _run(ready)
    rid = run["id"]
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "full_name": "Mallory Mal", "email": "mallory@example.com", "country_code": "+91", "phone": "9876543210",
        "state": "Maharashtra", "city": "Pune", "password": STRONG_PASSWORD})
    login(client, "mallory@example.com")
    h = csrf(client)
    assert client.get(f"/api/analysis/{rid}").status_code == 404
    assert client.get(f"/api/analysis/{rid}/raw").status_code == 404
    assert client.get(f"/api/analysis/{rid}/memo").status_code == 404
    assert client.post(f"/api/analysis/{rid}/dscr", headers=h, json=DSCR).status_code == 404
    assert client.post(f"/api/analysis/{rid}/assistant/ask", headers=h, json={"question": "q"}).status_code == 404
    assert client.get("/api/history").json() == []
    assert client.get("/api/analysis/not-an-id").status_code == 404


def test_analysis_endpoints_need_a_session_and_csrf(ready, client):
    run = _run(ready)
    assert ready.post("/api/analysis").status_code == 403  # no CSRF header
    assert ready.post(f"/api/analysis/{run['id']}/dscr", json=DSCR).status_code == 403
    client.cookies.clear()
    assert client.get(f"/api/analysis/{run['id']}").status_code == 401
