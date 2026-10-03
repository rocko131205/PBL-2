"""Docker entry point: start the /metrics endpoint for Prometheus, then run Streamlit.

Both run in this one process, so /metrics shows the numbers app.py records
(finveritas/shared/metrics.py). Starting it here rather than in app.py means it is up as
soon as the container starts, before anyone visits the app.

    python -m finveritas.serve
"""
import os
import sys

from prometheus_client import start_http_server
from streamlit.web import cli

import finveritas.shared.metrics  # noqa: F401  creates the page-run counters at 0 from boot

if __name__ == "__main__":
    start_http_server(9464)  # http://<app>:9464/metrics
    sys.argv = ["streamlit", "run", "app.py",
                "--server.address=0.0.0.0", f"--server.port={os.getenv('PORT', '8501')}"]
    sys.exit(cli.main())
