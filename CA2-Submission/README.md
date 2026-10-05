# FinVeritas · DevOps CA2 submission

Everything to be submitted for DevOps CA2, one folder per assignment task.
Project: FinVeritas, a Streamlit credit-risk analysis app ·
repository `github.com/rocko131205/PBL-2`, branch `DevOps-CA2`.

**Live app: <https://finveritas.onrender.com>**

## Proof that the pipeline deploys it

- Every push to `DevOps-CA2` runs **Test → Build → Deploy** in GitHub Actions
  ([`ci-cd.yml`](1-Deployment-CICD/ci-cd.yml)). Build also publishes the image to GHCR as
  `ghcr.io/rocko131205/pbl-2:sha-<commit>`.
- The Deploy job calls Render's deploy hook. Render's own Auto-Deploy is **off**, so a push
  that fails its tests never reaches the live app. In Render, each deploy is listed as
  triggered by the deploy hook.
- Render builds the same `Dockerfile` and switches traffic to the new version only once
  `/_stcore/health` answers, so the site stays up during a deploy.
- The free instance sleeps after 15 idle minutes, so the first visit can take about a minute.

## Deliverables

| # | Task | Required deliverable | Files in this folder |
|---|------|----------------------|----------------------|
| 1 | Deployment (CI/CD) | Workflow file and a pipeline diagram | [`1-Deployment-CICD/ci-cd.yml`](1-Deployment-CICD/ci-cd.yml), [`pipeline-diagram.png`](1-Deployment-CICD/pipeline-diagram.png) |
| 2 | Config management / IaC | Playbook and the inventory file | [`2-Config-Management-Ansible/site.yml`](2-Config-Management-Ansible/site.yml), [`inventory.ini`](2-Config-Management-Ansible/inventory.ini) |
| 3 | Containers and orchestration | Dockerfile, Deployment and Service YAMLs, screenshots of `kubectl rollout status` / `rollout undo` | [`3-Containers-Kubernetes/`](3-Containers-Kubernetes): `Dockerfile`, `deployment.yaml`, `service.yaml`, `screenshots/k8s-1…3` |
| 4 | Monitoring | Dashboard screenshots (uptime, latency, error rate) | [`4-Monitoring/screenshots/`](4-Monitoring/screenshots), plus the setup in [`4-Monitoring/config/`](4-Monitoring/config) |
| 5 | Reflection and report | Slides and written documentation | [`5-Reflection-and-Report/FinVeritas-CA2-Slides.pdf`](5-Reflection-and-Report/FinVeritas-CA2-Slides.pdf) (5 slides), [`FinVeritas-CA2-Report.pdf`](5-Reflection-and-Report/FinVeritas-CA2-Report.pdf) |

## What each screenshot shows

| File | Shows |
|------|-------|
| `k8s-1-deploy-v1.png` | `kubectl apply`, then `kubectl rollout status` until 2 pods of v1 are ready |
| `k8s-2-rolling-update.png` | `kubectl set image` to v2: a new pod starts beside the old ones, `rollout status` follows the update |
| `k8s-3-rollout-undo.png` | `kubectl rollout history`, `kubectl rollout undo`, `rollout status`: back on v1 |
| `monitoring-1-dashboard.png` | The Grafana dashboard after a live run: an error spike, an outage, and recovery |
| `monitoring-2-app-down.png` | The dashboard during the outage: status DOWN |
| `monitoring-3-prometheus-target.png` | Prometheus reading the app's `/metrics` endpoint: target UP |

## Notes

- These are copies of the working files in the repository. The originals are
  `.github/workflows/ci-cd.yml`, `deploy/ansible/`, `Dockerfile`, `deploy/k8s/`,
  `deploy/monitoring/` and `finveritas/shared/metrics.py`; run everything from there.
- In `4-Monitoring/config/`, `metrics.py` is the code that exposes the app's metrics,
  `prometheus.yml` tells Prometheus where to read them, and `grafana-dashboard.json` is the
  dashboard itself.
- The screenshots exist only in this folder; the docs in the repository link to them here.
- The full explanation of every task is in the report and in `docs/` of the repository
  (`CI_CD.md`, `KUBERNETES.md`, `MONITORING.md`, `REPORT.md`).
