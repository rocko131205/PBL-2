"""Ingestion API: the three sources, the review endpoints, validation and per-user isolation."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from api import views, workspace
from api.main import app
from api.routers import ingest

from .conftest import STRONG_PASSWORD, csrf, login

# current_assets / current_liabilities are deliberately absent -> the "missing data" flow.
CSV = (
    "period,revenue,operating_income,total_assets,total_liabilities,equity\n"
    "2022-FY,1000000,150000,2000000,1200000,800000\n"
    "2023-FY,1200000,190000,2300000,1350000,950000\n"
    "2024-FY,1500000,260000,2700000,1500000,1200000\n"
)


def _csv_upload(client, text=CSV, name="acme.csv", company="Acme Pvt Ltd", currency="INR"):
    return client.post(
        "/api/ingest/csv", headers=csrf(client),
        files={"file": (name, io.BytesIO(text.encode()), "text/csv")},
        data={"company_name": company, "currency": currency},
    )


@pytest.fixture
def signed_in(client, user):
    login(client)
    return client


# ── CSV ─────────────────────────────────────────────────────────────────────

def test_csv_load_returns_cards_readiness_and_preview(signed_in):
    r = _csv_upload(signed_in)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["loaded"] and body["source"] == "csv"
    assert body["entity"] == {"name": "Acme Pvt Ltd", "currency": "INR"}
    revenue = next(c for c in body["cards"] if c["field"] == "revenue")
    assert revenue["period"] == "2024-FY" and revenue["value"] == 1_500_000
    assert revenue["display"] == "₹15.00 L"
    assert revenue["change_pct"] == pytest.approx(50.0)
    assert [p["period"] for p in revenue["series"]] == ["2022-FY", "2023-FY", "2024-FY"]
    assert body["readiness"]["missing_fields"] == ["current_assets", "current_liabilities"]
    assert not body["readiness"]["complete"]
    assert "Liquidity agent" in body["readiness"]["skipped_agents"]
    assert body["periods"] == ["2022-FY", "2023-FY", "2024-FY"]
    assert body["scale"]["applicable"] is True


def test_csv_requires_company_name_and_known_currency(signed_in):
    assert _csv_upload(signed_in, company="   ").status_code == 422
    assert _csv_upload(signed_in, currency="XXX").status_code == 422


def test_csv_with_no_values_is_a_friendly_422(signed_in):
    r = _csv_upload(signed_in, text="period,revenue\n2023-FY,\n")
    assert r.status_code == 422 and "blank" in r.json()["detail"].lower()


@pytest.mark.parametrize("name,content", [
    ("evil.exe", b"MZ\x90\x00"), ("data.csv", b"\x00\x01\x02binary"), ("empty.csv", b""),
    ("fake.xlsx", b"just text"),
])
def test_bad_spreadsheets_are_rejected(signed_in, name, content):
    r = signed_in.post("/api/ingest/csv", headers=csrf(signed_in),
                       files={"file": (name, io.BytesIO(content), "application/octet-stream")},
                       data={"company_name": "X", "currency": "INR"})
    assert r.status_code == 422


def test_oversized_upload_is_rejected_without_parsing(signed_in, monkeypatch):
    monkeypatch.setattr(ingest, "MAX_SHEET_BYTES", 100)
    r = _csv_upload(signed_in, text=CSV * 5)
    assert r.status_code == 422 and "exceeds" in r.json()["detail"]


def test_rejected_upload_is_audited(signed_in, mongo):
    _csv_upload(signed_in, name="evil.exe")
    assert mongo.audit_log.count_documents({"event": "upload_rejected"}) == 1


def test_csv_template_downloads(signed_in):
    r = signed_in.get("/api/ingest/csv-template")
    assert r.status_code == 200 and r.text.startswith("period,revenue")
    assert "attachment" in r.headers["content-disposition"]


# ── Ticker ──────────────────────────────────────────────────────────────────

FAKE_PAYLOAD = {
    "entity": {"entity_id": "TATA CONSULTANCY SERVICES LTD", "currency": "INR"},
    "time_series": {
        "revenue": [{"period": "2023-FY", "value": float("nan")}, {"period": "2024-FY", "value": 2.4e12}],
        "total_assets": [{"period": "2024-FY", "value": 1.6e12}],
    },
}


def test_ticker_load_cleans_provider_output(signed_in, monkeypatch):
    monkeypatch.setattr(ingest, "fetch_by_ticker", lambda t: {**FAKE_PAYLOAD, "entity": dict(FAKE_PAYLOAD["entity"])})
    r = signed_in.post("/api/ingest/ticker", headers=csrf(signed_in), json={"ticker": " tcs.ns "})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source_label"] == "yfinance · TCS.NS" and body["ticker"] == "TCS.NS"
    assert body["entity"]["name"] == "TATA CONSULTANCY SERVICES LTD"
    assert body["scale"]["applicable"] is False  # tickers are already absolute


@pytest.mark.parametrize("ticker", ["", "   ", "../../etc", "AAPL&apikey=x", "A" * 40, "AAPL/../x", "a b"])
def test_invalid_tickers_never_reach_the_provider(signed_in, monkeypatch, ticker):
    monkeypatch.setattr(ingest, "fetch_by_ticker", lambda t: pytest.fail("provider must not be called"))
    assert signed_in.post("/api/ingest/ticker", headers=csrf(signed_in), json={"ticker": ticker}).status_code == 422


def test_provider_failure_hides_internals(signed_in, monkeypatch):
    def boom(_):
        raise RuntimeError("HTTPSConnectionPool(host='query1.finance.yahoo.com'): secret-key=abc123")
    monkeypatch.setattr(ingest, "fetch_by_ticker", boom)
    r = signed_in.post("/api/ingest/ticker", headers=csrf(signed_in), json={"ticker": "AAPL"})
    assert r.status_code == 500
    assert "abc123" not in r.text and "yahoo" not in r.text and "reference" in r.json()["detail"]


# ── PDF ─────────────────────────────────────────────────────────────────────

def test_pdf_rejects_non_pdf_content(signed_in):
    r = signed_in.post("/api/ingest/pdf", headers=csrf(signed_in),
                       files=[("files", ("report.pdf", io.BytesIO(b"not a pdf at all"), "application/pdf"))])
    assert r.status_code == 422 and "not a valid PDF" in r.json()["detail"]


def test_pdf_rejects_too_many_files(signed_in):
    files = [("files", (f"{i}.pdf", io.BytesIO(b"%PDF-"), "application/pdf")) for i in range(5)]
    assert signed_in.post("/api/ingest/pdf", headers=csrf(signed_in), files=files).status_code == 422


def test_pdf_success_path_stores_merged_payload(signed_in, monkeypatch):
    from finveritas.security.uploads import ValidatedFile
    monkeypatch.setattr(ingest, "validate_pdf_batch", lambda raw: [ValidatedFile(d, n, "pdf") for d, n in raw])
    monkeypatch.setattr(ingest, "parse_pdf_to_json", lambda uploads: (FAKE_PAYLOAD, None, {}))
    files = [("files", ("is.pdf", io.BytesIO(b"%PDF-1"), "application/pdf")),
             ("files", ("bs.pdf", io.BytesIO(b"%PDF-2"), "application/pdf"))]
    r = signed_in.post("/api/ingest/pdf", headers=csrf(signed_in), files=files)
    assert r.status_code == 200 and r.json()["source_label"] == "2 Bloomberg PDF(s)"


# ── Auth, CSRF, throttling, isolation ───────────────────────────────────────

def test_endpoints_require_a_session(client):
    assert client.get("/api/workspace").status_code == 401
    assert client.post("/api/ingest/ticker", json={"ticker": "AAPL"}).status_code == 401


def test_writes_without_csrf_header_are_refused(signed_in):
    r = signed_in.post("/api/ingest/ticker", json={"ticker": "AAPL"})
    assert r.status_code == 403


def test_ingestion_is_rate_limited_per_user(signed_in, monkeypatch):
    monkeypatch.setattr(ingest, "INGEST_MAX", 2)
    monkeypatch.setattr(ingest, "fetch_by_ticker", lambda t: {**FAKE_PAYLOAD, "entity": dict(FAKE_PAYLOAD["entity"])})
    codes = [signed_in.post("/api/ingest/ticker", headers=csrf(signed_in), json={"ticker": "AAPL"}).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]


def test_users_cannot_see_each_others_workspace(client, user):
    login(client)
    assert _csv_upload(client).status_code == 200
    client.post("/api/auth/logout")

    other = client.post("/api/auth/register", json={
        "full_name": "Mallory Mal", "email": "mallory@example.com", "country_code": "+91", "phone": "9876543210",
        "state": "Maharashtra", "city": "Pune", "password": STRONG_PASSWORD})
    assert other.status_code == 201
    login(client, "mallory@example.com")
    assert client.get("/api/workspace").json() == {"loaded": False}
    assert client.get("/api/workspace/credibility").status_code == 404
    assert client.put("/api/workspace/qualitative", headers=csrf(client), json={"text": "hijack"}).status_code == 404


# ── Review endpoints ────────────────────────────────────────────────────────

def test_empty_workspace_and_clear(signed_in):
    assert signed_in.get("/api/workspace").json() == {"loaded": False}
    _csv_upload(signed_in)
    assert signed_in.delete("/api/workspace", headers=csrf(signed_in)).status_code == 204
    assert signed_in.get("/api/workspace").json() == {"loaded": False}


def test_loading_new_data_replaces_the_old_dataset(signed_in, monkeypatch):
    _csv_upload(signed_in)
    monkeypatch.setattr(ingest, "fetch_by_ticker", lambda t: {**FAKE_PAYLOAD, "entity": dict(FAKE_PAYLOAD["entity"])})
    signed_in.post("/api/ingest/ticker", headers=csrf(signed_in), json={"ticker": "TCS.NS"})
    assert signed_in.get("/api/workspace").json()["source"] == "ticker"


def test_scale_rescales_displayed_cards_but_not_stored_data(signed_in, mongo):
    _csv_upload(signed_in)
    r = signed_in.put("/api/workspace/scale", headers=csrf(signed_in), json={"multiplier": 1e6})
    rev = next(c for c in r.json()["cards"] if c["field"] == "revenue")
    assert rev["value"] == 1_500_000 * 1e6 and rev["display"] == "₹150,000.00 Cr"
    stored = mongo.workspaces.find_one({})["payload"]["time_series"]["revenue"][-1]["value"]
    assert stored == 1_500_000  # raw value untouched; scale is applied on read


@pytest.mark.parametrize("bad", [3.0, 0.0, -1e6, 1e12])
def test_scale_rejects_unsupported_multipliers(signed_in, bad):
    _csv_upload(signed_in)
    assert signed_in.put("/api/workspace/scale", headers=csrf(signed_in), json={"multiplier": bad}).status_code == 422


def test_scale_not_allowed_for_ticker_data(signed_in, monkeypatch):
    monkeypatch.setattr(ingest, "fetch_by_ticker", lambda t: {**FAKE_PAYLOAD, "entity": dict(FAKE_PAYLOAD["entity"])})
    signed_in.post("/api/ingest/ticker", headers=csrf(signed_in), json={"ticker": "TCS.NS"})
    assert signed_in.put("/api/workspace/scale", headers=csrf(signed_in), json={"multiplier": 1e7}).status_code == 400


def test_qualitative_context_is_saved(signed_in):
    _csv_upload(signed_in)
    signed_in.put("/api/workspace/qualitative", headers=csrf(signed_in), json={"text": "Guided to 20% growth."})
    assert signed_in.get("/api/workspace").json()["qualitative"] == "Guided to 20% growth."


def test_credibility_is_computed_cached_and_reset_by_new_data(signed_in, monkeypatch):
    _csv_upload(signed_in)
    first = signed_in.get("/api/workspace/credibility").json()
    assert 0 <= first["score"] <= 100 and first["confidence"] in {"HIGH", "MEDIUM", "LOW"}
    assert {c["status"] for c in first["checks"]} <= {"pass", "warn", "fail", "skip"}
    monkeypatch.setattr(ingest, "run_verification", lambda **k: pytest.fail("should be served from cache"))
    assert signed_in.get("/api/workspace/credibility").json() == first
    assert signed_in.get("/api/workspace").json()["credibility"] == first


# ── Supplement (fill in missing fields) ─────────────────────────────────────

def test_supplement_fills_missing_fields_and_invalidates_credibility(signed_in):
    _csv_upload(signed_in)
    signed_in.get("/api/workspace/credibility")
    r = signed_in.post("/api/workspace/supplement/apply", headers=csrf(signed_in), json={"values": {
        "current_assets": {"2022-FY": "900,000", "2023-FY": 1000000, "2024-FY": "1100000"},
        "current_liabilities": {"2022-FY": "500000", "2023-FY": "", "2024-FY": None},
    }})
    assert r.status_code == 200, r.text
    body = r.json()
    # a field counts as present as soon as it has any value
    assert body["readiness"]["missing_fields"] == []
    assert body["readiness"]["complete"] is True
    assert body["credibility"] is None


def test_supplement_rejects_bad_numbers_unknown_periods_and_unneeded_fields(signed_in):
    _csv_upload(signed_in)
    r = signed_in.post("/api/workspace/supplement/apply", headers=csrf(signed_in), json={"values": {
        "current_assets": {"2022-FY": "abc", "1999-FY": "5", "2023-FY": "nan"},
        "revenue": {"2022-FY": "1"},
    }})
    assert r.status_code == 422
    errors = r.json()["errors"]
    assert errors["current_assets|2022-FY"] and errors["current_assets|1999-FY"] and errors["current_assets|2023-FY"]
    assert errors["revenue"]


def test_supplement_with_nothing_entered_is_rejected(signed_in):
    _csv_upload(signed_in)
    r = signed_in.post("/api/workspace/supplement/apply", headers=csrf(signed_in),
                       json={"values": {"current_assets": {"2022-FY": ""}}})
    assert r.status_code == 422


def test_autofetch_only_for_tickers_with_a_configured_provider(signed_in, monkeypatch):
    _csv_upload(signed_in)
    assert signed_in.post("/api/workspace/supplement/autofetch", headers=csrf(signed_in),
                          json={"provider": "fmp"}).status_code == 400
    monkeypatch.setattr(ingest, "fetch_by_ticker", lambda t: {**FAKE_PAYLOAD, "entity": dict(FAKE_PAYLOAD["entity"])})
    signed_in.post("/api/ingest/ticker", headers=csrf(signed_in), json={"ticker": "TCS.NS"})
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    assert signed_in.post("/api/workspace/supplement/autofetch", headers=csrf(signed_in),
                          json={"provider": "fmp"}).status_code == 400
    assert signed_in.post("/api/workspace/supplement/autofetch", headers=csrf(signed_in),
                          json={"provider": "evil"}).status_code == 422


def test_autofetch_returns_prefill_values_and_hides_provider_errors(signed_in, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "k" * 10)
    monkeypatch.setattr(ingest, "fetch_by_ticker", lambda t: {**FAKE_PAYLOAD, "entity": dict(FAKE_PAYLOAD["entity"])})
    signed_in.post("/api/ingest/ticker", headers=csrf(signed_in), json={"ticker": "TCS.NS"})
    seen = {}

    def fake(**kw):
        seen.update(kw)
        return ({"current_assets": [{"period": "2024-FY", "value": 5e11}]}, ["current_assets"],
                ["FMP: 401 for https://x/?apikey=kkkkkkkkkk"])
    monkeypatch.setattr(ingest, "auto_fetch_missing_fields", fake)
    r = signed_in.post("/api/workspace/supplement/autofetch", headers=csrf(signed_in), json={"provider": "fmp"})
    assert r.status_code == 200
    assert r.json()["values"] == {"current_assets": {"2024-FY": 5e11}}
    assert "kkkkkkkkkk" not in r.text and "apikey" not in r.text
    assert seen["ticker"] == "TCS.NS" and seen["fmp_api_key"] == "k" * 10 and seen["av_api_key"] is None


# ── Pure helpers ────────────────────────────────────────────────────────────

def test_latest_value_skips_future_projections():
    rows = [("2023-FY", 1.0), ("2024-FY", 2.0), ("2099-FY", 9.0)]
    assert views.latest_value(rows) == (2.0, "2024-FY")
    assert views.latest_value([]) == (None, "—")


def test_periods_sort_chronologically_with_fy_after_quarters():
    payload = {"time_series": {"revenue": [{"period": "2024-FY", "value": 1}, {"period": "2024-Q1", "value": 1},
                                           {"period": "2023-FY", "value": 1}]}}
    assert views.periods_in(payload) == ["2023-FY", "2024-Q1", "2024-FY"]


@pytest.mark.parametrize("raw,ok", [("1,50,000", True), ("  12.5 ", True), (7, True), ("abc", False),
                                    ("nan", False), ("inf", False), ("", False)])
def test_parse_amount(raw, ok):
    if ok:
        assert views.parse_amount(raw) == float(str(raw).replace(",", ""))
    else:
        with pytest.raises(ValueError):
            views.parse_amount(raw)


def test_clean_removes_nan_numpy_and_non_string_keys():
    import numpy as np
    out = workspace.clean({1: np.float64("nan"), "a": [np.int64(3), float("inf")], "b": np.float32(1.5)})
    assert out == {"1": None, "a": [3, None], "b": 1.5}
