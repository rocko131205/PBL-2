"""Stored / reflected XSS in HTML rendered with unsafe_allow_html (FV-10)."""
from __future__ import annotations

from bson import ObjectId

from finveritas.auth import pages
from finveritas.shared.components import agent_tooltip_html

PAYLOAD = '<img src=x onerror="alert(document.cookie)">'


def test_file_history_escapes_values_from_uploaded_files(mongo, monkeypatch):
    uid = ObjectId()
    mongo.file_history.insert_one({
        "user_id": uid, "source_type": "csv", "source_label": PAYLOAD,
        "entity_name": PAYLOAD, "credibility_score": PAYLOAD,
    })
    rendered: list[str] = []
    monkeypatch.setattr(pages.st, "markdown", lambda body, **k: rendered.append(body))
    pages.page_history(str(uid))
    html_out = "".join(rendered)
    assert "<img" not in html_out and "&lt;img" in html_out


def test_file_history_only_shows_own_records(mongo, monkeypatch):
    me, other = ObjectId(), ObjectId()
    mongo.file_history.insert_one({"user_id": other, "entity_name": "OtherUserCo", "source_type": "pdf"})
    rendered: list[str] = []
    monkeypatch.setattr(pages.st, "markdown", lambda body, **k: rendered.append(body))
    pages.page_history(str(me))
    assert "OtherUserCo" not in "".join(rendered)


def test_workflow_tooltip_escapes_errors_and_analysis():
    out = agent_tooltip_html(PAYLOAD, {"error": PAYLOAD})
    assert "<img" not in out
    out = agent_tooltip_html("Agent", {"metrics": {PAYLOAD: PAYLOAD}, "analysis": PAYLOAD})
    assert "<img" not in out
