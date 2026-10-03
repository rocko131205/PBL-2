# Monitoring (Prometheus + Grafana)

The app exposes its own metrics at `/metrics`. **Prometheus** collects them every 5 seconds,
and a **Grafana** dashboard shows **uptime, latency and error rate**. One command starts the
app, Prometheus and Grafana together.

| File | What it does |
|------|--------------|
| [`finveritas/shared/metrics.py`](../finveritas/shared/metrics.py) | Defines the app's metrics, and `track_page_run()`, which counts and times every page run |
| [`app.py`](../app.py) (last lines) | Wraps each page run in `track_page_run()` |
| [`finveritas/serve.py`](../finveritas/serve.py) | The Docker entry point: starts `/metrics` on port 9464, then Streamlit, in one process |
| [`deploy/monitoring/docker-compose.yml`](../deploy/monitoring/docker-compose.yml) | Runs the app, Prometheus and Grafana |
| [`deploy/monitoring/prometheus.yml`](../deploy/monitoring/prometheus.yml) | Tells Prometheus to read `app:9464/metrics` every 5 seconds |
| [`deploy/monitoring/grafana/`](../deploy/monitoring/grafana) | Connects Grafana to Prometheus and loads the dashboard ([`finveritas.json`](../deploy/monitoring/grafana/finveritas.json)) |
| [`tests/test_metrics.py`](../tests/test_metrics.py) | Checks that runs are counted and that only real errors count as errors |

---

## How it works

```
 Browser ──▶ app :8501 (Streamlit)          Prometheus :9090           Grafana :3000
             │ every page run is counted    reads /metrics every 5 s   queries Prometheus,
             │ and timed (metrics.py)  ◀─── and stores the numbers ◀── draws the dashboard
             └ /metrics :9464 (serve.py)
```

A **page run** is Streamlit running `app.py` once. That happens on every page load and every
click, so it plays the role that a "request" plays in other web apps.

| Metric | Type | Meaning |
|--------|------|---------|
| `finveritas_page_runs_total` | Counter | Page runs so far |
| `finveritas_page_errors_total` | Counter | Page runs that failed with an error. `st.stop()` and `st.rerun()` are not errors |
| `finveritas_page_run_seconds` | Histogram | How long each page run took |
| `up` | Added by Prometheus | 1 if the last read of `/metrics` worked, 0 if the app was unreachable |

## The dashboard

| Panel | What it shows | Query (PromQL) |
|-------|---------------|----------------|
| **Status** | UP or DOWN right now | `up{job="finveritas"}` |
| **Uptime** | % of checks in the selected time range that found the app up | `avg_over_time(up{job="finveritas"}[$__range]) * 100` |
| **Latency** | Median and p95 page-run time | `histogram_quantile(0.95, sum by (le) (rate(finveritas_page_run_seconds_bucket[1m])))` |
| **Error rate** | Failed page runs ÷ all page runs | `sum(rate(finveritas_page_errors_total[1m])) / sum(rate(finveritas_page_runs_total[1m]))` |
| **Traffic** | Page runs per second, all and failed | `sum(rate(finveritas_page_runs_total[1m]))` |

p95 means 95% of page runs were faster than this. It shows the slow cases that an average hides.

---

## Run it yourself

From the repo root (needs Docker Desktop):

```sh
docker compose -f deploy/monitoring/docker-compose.yml up -d --build
```

Then open the app at http://localhost:8501 and click around. The dashboard at
http://localhost:3000 fills in within a minute. Prometheus is at http://localhost:9090.
To stop everything:

```sh
docker compose -f deploy/monitoring/docker-compose.yml down
```

This stack has no database, so the app's pages work but logging in fails, which is how the
errors in the screenshots were produced. To monitor the full app, add your settings to the
`app` service in `docker-compose.yml`:

```yaml
    env_file: ../../.env
```
