"""Prometheus metrics for FinVeritas.

A "page run" is Streamlit running app.py once, which happens on every page load and every
click. Each run is counted and timed here; finveritas/serve.py publishes the numbers at
http://<app>:9464/metrics for Prometheus. The Grafana dashboard turns them into latency
and error rate (docs/MONITORING.md).
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import Counter, Histogram

PAGE_RUNS = Counter("finveritas_page_runs_total", "Page runs: one per page load or click.")
PAGE_ERRORS = Counter("finveritas_page_errors_total", "Page runs that failed with an error.")
PAGE_RUN_SECONDS = Histogram("finveritas_page_run_seconds", "How long one page run takes.")


@contextmanager
def track_page_run() -> Iterator[None]:
    """Count and time one page run, and count it as an error if it raises.

    st.stop() and st.rerun() end a run by raising BaseException subclasses, not Exception,
    so they are not counted as errors.
    """
    PAGE_RUNS.inc()
    start = time.perf_counter()
    try:
        yield
    except Exception:
        PAGE_ERRORS.inc()
        raise
    finally:
        PAGE_RUN_SECONDS.observe(time.perf_counter() - start)
