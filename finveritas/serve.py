"""Container entry point: start the Prometheus /metrics endpoint, then run Streamlit in this process.

Streamlit only executes app code when a visitor connects, so starting /metrics from app.py
would leave it down after every restart until the first page view. Starting it here makes it
available from boot, and running Streamlit in the same process means the app's code records
into the same metrics registry.

    python -m finveritas.serve        (what the Docker image runs)
"""
from __future__ import annotations

import os
import sys

from finveritas.shared.metrics import start_metrics_server


def streamlit_argv() -> list[str]:
    return [
        "streamlit", "run", "app.py",
        f"--server.port={os.getenv('PORT', '8501')}",
        "--server.address=0.0.0.0",
        "--server.headless=true",
        "--server.fileWatcherType=none",
    ]


def main() -> None:
    start_metrics_server()
    from streamlit.web import cli  # the same entry point as the `streamlit` command

    sys.argv = streamlit_argv()
    sys.exit(cli.main())


if __name__ == "__main__":
    main()
