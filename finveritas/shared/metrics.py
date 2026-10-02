"""Prometheus metrics for FinVeritas.

Served on a separate port (METRICS_PORT, e.g. 9464) so Prometheus can scrape them
without going through the public app port. When METRICS_PORT is unset — local runs,
tests — nothing listens and the counters below are just in-memory no-ops.

Labels come from fixed sets only: never emails, user ids or other user data.
"""
from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import Counter, Gauge, Histogram, start_http_server

try:  # st.stop() / st.rerun() raise these to end a run — they are not errors
    from streamlit.runtime.scriptrunner_utils.exceptions import ScriptControlException as _ScriptControl
except ImportError:  # pragma: no cover — older Streamlit layouts
    _ScriptControl = None

PAGE_RENDERS = Counter(
    "finveritas_page_renders_total",
    "Streamlit script runs (one per user interaction), by page and outcome.",
    ["page", "outcome"],
)
PAGE_RENDER_SECONDS = Histogram(
    "finveritas_page_render_seconds",
    "Time to run the app script for one user interaction.",
    ["page"],
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
LOGINS = Counter(
    "finveritas_logins_total",
    "Login attempts by result.",
    ["result"],  # success · mfa_required · failure · locked
)
BUILD_INFO = Gauge(
    "finveritas_build_info",
    "Always 1; the version label identifies the running build.",
    ["version"],
)

# Streamlit page name → metric label (anything else is "other", keeping cardinality bounded).
_PAGE_LABELS = {
    "login": "login",
    "register": "register",
    "forgot": "forgot_password",
    "Upload Statement": "upload",
    "Financial Analysis": "analysis",
    "Agent Workflow": "workflow",
    "Basel III Alignment": "basel",
    "My File History": "history",
    "Security Settings": "security_settings",
    "Security Dashboard": "security_dashboard",
}

_lock = threading.Lock()
_server_started = False
_render = threading.local()   # each Streamlit run executes on one thread


def start_metrics_server() -> bool:
    """Start the /metrics endpoint once per process if METRICS_PORT is set. Safe to call every run."""
    global _server_started
    port = os.getenv("METRICS_PORT", "").strip()
    if not port:
        return False
    with _lock:
        if not _server_started:
            start_http_server(int(port), addr=os.getenv("METRICS_ADDR", "0.0.0.0"))  # nosec B104 — scrape port, not public
            BUILD_INFO.labels(version=os.getenv("APP_VERSION", "dev")).set(1)
            _server_started = True
    return True


def page_label(page: str | None) -> str:
    return _PAGE_LABELS.get(page or "", "other")


def _is_script_control(exc: BaseException) -> bool:
    if _ScriptControl is not None:
        return isinstance(exc, _ScriptControl)
    return type(exc).__name__ in {"StopException", "RerunException"}


def set_render_page(page: str | None) -> None:
    """Called by the app as soon as it knows which page this run renders."""
    _render.page = page


@contextmanager
def track_page_render() -> Iterator[None]:
    """Time one script run and count it as ok/error, labelled with the page set via set_render_page().

    The label is recorded during the run rather than read from st.session_state here: after
    st.stop(), every Streamlit call raises StopException again, so this block must not call
    Streamlit at all.
    """
    _render.page = None
    start = time.perf_counter()
    outcome = "ok"
    try:
        yield
    except BaseException as exc:
        if not _is_script_control(exc):
            outcome = "error"
        raise
    finally:
        page = page_label(getattr(_render, "page", None))
        PAGE_RENDERS.labels(page=page, outcome=outcome).inc()
        PAGE_RENDER_SECONDS.labels(page=page).observe(time.perf_counter() - start)
