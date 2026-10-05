# FinVeritas · DevOps CA2

FinVeritas is a Streamlit web app, built as our PBL project, that analyses a company's
financial statements for credit risk. It reads PDFs, spreadsheets or a stock ticker, computes
ratios, a credit scorecard and a debt-service schedule in Python, and uses an LLM only to
explain the computed numbers. Users and their history are stored in MongoDB.

For DevOps CA2 this branch, **`DevOps-CA2`**, takes the app from code in a repository to a
service that is **tested, built, deployed, orchestrated and monitored**.

**Live app: <https://finveritas.onrender.com>**. It is deployed to Render by the GitHub Actions
pipeline after every push to `DevOps-CA2` that passes its tests. It runs on Render's free
plan, so the first visit after 15 idle minutes takes about a minute while the app wakes up.

## Group 34

| Name | PRN | GitHub |
|------|-----|--------|
| Anshul Ravindra Mandekar | 23070122033 | [AnshulMandekar](https://github.com/AnshulMandekar) |
| Arunabha Mukhopadhyay | 23070122049 | [Arunabha-Mukhopadhyay](https://github.com/Arunabha-Mukhopadhyay) |
| Avi S Gupta | 23070122060 | [rocko131205](https://github.com/rocko131205) |
| Ayaan Rukadikar | 23070122063 | [AyaanRukadikar](https://github.com/AyaanRukadikar) |

---

## Deliverables

| Step | Task | Submission files | Working files | Explained in |
|------|------|------------------|---------------|--------------|
| 1 | Deployment strategy (CI/CD) | [`CA2-Submission/1-Deployment-CICD/`](CA2-Submission/1-Deployment-CICD): workflow + pipeline diagram | [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml) | [`docs/CI_CD.md`](docs/CI_CD.md) |
| 2 | Configuration management (Ansible) | [`CA2-Submission/2-Config-Management-Ansible/`](CA2-Submission/2-Config-Management-Ansible): playbook + inventory | [`deploy/ansible/`](deploy/ansible) | header of [`site.yml`](deploy/ansible/site.yml) |
| 3 | Containers and orchestration | [`CA2-Submission/3-Containers-Kubernetes/`](CA2-Submission/3-Containers-Kubernetes): Dockerfile, Deployment, Service, rollout screenshots | [`Dockerfile`](Dockerfile), [`deploy/k8s/`](deploy/k8s) | [`docs/KUBERNETES.md`](docs/KUBERNETES.md) |
| 4 | Monitoring (Prometheus + Grafana) | [`CA2-Submission/4-Monitoring/`](CA2-Submission/4-Monitoring): dashboard screenshots + config | [`deploy/monitoring/`](deploy/monitoring), [`finveritas/shared/metrics.py`](finveritas/shared/metrics.py) | [`docs/MONITORING.md`](docs/MONITORING.md) |
| 5 | Reflection and report | [`CA2-Submission/5-Reflection-and-Report/`](CA2-Submission/5-Reflection-and-Report): 5 slides + report PDF | – | [`docs/REPORT.md`](docs/REPORT.md) |
| 6 | Bonus: external DevOps challenge | [`CA2-Submission/6-Bonus-DevOps-Challenge/`](CA2-Submission/6-Bonus-DevOps-Challenge): PipePulse on Devpost, submitted to Syntax Summit, with screenshots | – | its [`README.md`](CA2-Submission/6-Bonus-DevOps-Challenge/README.md) |

[`CA2-Submission/README.md`](CA2-Submission/README.md) describes every file and screenshot.

## Repository layout

```
.
├── app.py                        Streamlit entry point
├── finveritas/                   the app's code; serve.py starts /metrics, then Streamlit
├── tests/                        154 pytest tests, run by the pipeline on every push
├── requirements.txt
├── Dockerfile, .dockerignore     the container image (Render builds the same Dockerfile)
├── .github/workflows/ci-cd.yml   Step 1: test → build → deploy
├── deploy/
│   ├── ansible/                  Step 2: site.yml + inventory.ini
│   ├── k8s/                      Step 3: deployment.yaml + service.yaml
│   └── monitoring/               Step 4: Prometheus + Grafana with Docker Compose
├── docs/                         CI_CD.md · KUBERNETES.md · MONITORING.md · REPORT.md
└── CA2-Submission/               one folder per step: files, screenshots, slides, report
```

---

## Run it locally

```sh
git clone -b DevOps-CA2 https://github.com/rocko131205/PBL-2.git
cd PBL-2
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py                                    # open http://localhost:8501
pytest                                                  # 154 tests
```

Or as a container: `docker build -t finveritas . && docker run --rm -p 8501:8501 --env-file .env finveritas`.

### Environment variables (`.env` in the repo root)

```env
# Security and database
JWT_SECRET=a_random_string_of_at_least_32_characters
MONGO_URI=mongodb+srv://...
MONGO_DB_NAME=finveritas

# Email OTP for password reset
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASS=your_app_password

# LLM (any OpenAI-compatible endpoint)
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-120b
LLM_API_KEY=your_key

# Optional supplemental data
NEWSAPI_KEY=...
FMP_API_KEY=...
```

`.env` is in `.gitignore` and `.dockerignore`, so it is never committed or built into an image.
On Render the same variables are set in the service's *Environment* settings. The app works
without the LLM; only the AI explanations need it.

---

FinVeritas is decision support for a qualified analyst, not a binding credit decision. All data
comes from public filings and Yahoo Finance, for educational use.
