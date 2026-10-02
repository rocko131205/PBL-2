"""Prometheus instrumentation: page-render timing/outcomes, login results, opt-in endpoint."""
from __future__ import annotations

import sys

import pytest
from prometheus_client import REGISTRY

from finveritas.shared import metrics
from streamlit.runtime.scriptrunner_utils.exceptions import RerunException, StopException


def _value(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_successful_render_is_counted_and_timed():
    before = _value("finveritas_page_renders_total", page="analysis", outcome="ok")
    timed = _value("finveritas_page_render_seconds_count", page="analysis")
    with metrics.track_page_render():
        metrics.set_render_page("Financial Analysis")
    assert _value("finveritas_page_renders_total", page="analysis", outcome="ok") == before + 1
    assert _value("finveritas_page_render_seconds_count", page="analysis") == timed + 1


def test_uncaught_exception_counts_as_error_and_propagates():
    before = _value("finveritas_page_renders_total", page="login", outcome="error")
    with pytest.raises(RuntimeError):
        with metrics.track_page_render():
            metrics.set_render_page("login")
            raise RuntimeError("database unavailable")
    assert _value("finveritas_page_renders_total", page="login", outcome="error") == before + 1


@pytest.mark.parametrize("control", [StopException(), RerunException(None)])
def test_st_stop_and_rerun_are_not_errors(control):
    errors = _value("finveritas_page_renders_total", page="login", outcome="error")
    oks = _value("finveritas_page_renders_total", page="login", outcome="ok")
    with pytest.raises(type(control)):
        with metrics.track_page_render():
            metrics.set_render_page("login")
            raise control
    assert _value("finveritas_page_renders_total", page="login", outcome="error") == errors
    assert _value("finveritas_page_renders_total", page="login", outcome="ok") == oks + 1


@pytest.mark.parametrize("page, label", [
    ("Upload Statement", "upload"), ("forgot", "forgot_password"), (None, "other"),
    ("<script>alert(1)</script>", "other"), ("alice@example.com", "other"),
])
def test_page_labels_are_a_fixed_set(page, label):
    assert metrics.page_label(page) == label


def test_metrics_server_is_off_unless_configured(monkeypatch):
    monkeypatch.delenv("METRICS_PORT", raising=False)
    assert metrics.start_metrics_server() is False


def test_serve_starts_metrics_before_streamlit(monkeypatch):
    import streamlit.web.cli as cli
    from finveritas import serve

    calls = []
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setattr(sys, "argv", ["pytest"])
    monkeypatch.setattr(serve, "start_metrics_server", lambda: calls.append("metrics"))
    monkeypatch.setattr(cli, "main", lambda: calls.append(list(sys.argv)) or 0)
    with pytest.raises(SystemExit):
        serve.main()
    assert calls[0] == "metrics"
    assert calls[1][:3] == ["streamlit", "run", "app.py"]
    assert "--server.port=9999" in calls[1]


def test_page_label_resets_between_runs():
    with metrics.track_page_render():
        metrics.set_render_page("My File History")
    before = _value("finveritas_page_renders_total", page="other", outcome="ok")
    with metrics.track_page_render():
        pass  # e.g. a run stopped by the startup config check, before any page is chosen
    assert _value("finveritas_page_renders_total", page="other", outcome="ok") == before + 1
