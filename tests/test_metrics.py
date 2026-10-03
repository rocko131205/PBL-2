"""Page-run metrics: every run is counted and timed; only real exceptions count as errors."""
import pytest
from prometheus_client import REGISTRY
from streamlit.runtime.scriptrunner_utils.exceptions import StopException

from finveritas.shared.metrics import track_page_run


def _counts() -> tuple[float, float, float]:
    get = REGISTRY.get_sample_value
    return (get("finveritas_page_runs_total"), get("finveritas_page_errors_total"),
            get("finveritas_page_run_seconds_count"))


def test_ok_error_and_stop_runs():
    runs, errors, timed = _counts()

    with track_page_run():
        pass
    with pytest.raises(ValueError), track_page_run():
        raise ValueError("page crashed")
    with pytest.raises(StopException), track_page_run():
        raise StopException()  # what st.stop() raises: not an error

    assert _counts() == (runs + 3, errors + 1, timed + 3)
