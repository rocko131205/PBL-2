# Project Structure

All application code lives under one package, **`finveritas/`**, so the project root
stays clean. Inside, code is grouped by the **user journey**, in execution order.

```
PBL-2/                          ← repo root
├── app.py                      ← ENTRY POINT / router (auth gate, sidebar nav, dispatch)
├── requirements.txt
├── Dockerfile                  ← production image (built + deployed by .github/workflows/ci-cd.yml)
├── deploy/ansible/             ← self-hosted runtime: site.yml playbook + inventory.ini
├── deploy/k8s/                 ← Kubernetes: Deployment + Service (base/), overlays/, rollout demo
├── deploy/monitoring/          ← Prometheus + Grafana stack, dashboard JSON, alerts, synthetic users
├── docs/                       ← all documentation
├── finveritas/                 ← ALL source code
│   ├── serve.py                container entry point: /metrics, then Streamlit
│   │
│   ├── auth/                   ── 1. LOGIN / SIGNUP (runs first) ──────────────
│   │   ├── pages.py            login (+MFA step), register, forgot-password, history screens
│   │   ├── security_pages.py   Security Settings (MFA, sessions) + admin Security Dashboard
│   │   ├── controller.py       login/lockout, MFA, sessions, hardened OTP reset
│   │   ├── db.py               MongoDB users, history, sessions, rate limits, audit log
│   │   └── states.py           state/city data for the signup form
│   │
│   ├── ingestion/              ── 2. GET DATA IN (the Upload page) ────────────
│   │   ├── page.py             THE UPLOAD PAGE (PDF / ticker / CSV) + its helpers
│   │   ├── ticker.py           fetch listed-company financials by ticker (yfinance)
│   │   ├── spreadsheet.py      CSV/Excel loader + template
│   │   ├── supplemental.py     FMP / Alpha Vantage gap-fill
│   │   ├── credibility.py      data credibility scoring (0–100)
│   │   ├── normalize.py        raw payload → NormalizedCompanyRecord
│   │   ├── scale.py            detect "in millions/lakhs/crore" & rescale
│   │   └── pdf/                Bloomberg-PDF OCR chain (runs in this order)
│   │       ├── extractor.py    pdfplumber → PDFContent
│   │       ├── parser.py       PDFContent → ParsedStatement
│   │       ├── labels.py       Bloomberg label → canonical field
│   │       ├── builder.py      statements → company JSON
│   │       └── loader.py       parses uploaded PDFs into the payload (in memory)
│   │
│   ├── analysis/               ── 3. ANALYSE & PRESENT (the results) ──────────
│   │   ├── page.py             the results screens (verdict, scorecard, DSCR,
│   │   │                       metrics, anomalies, forecast, AI, memo, Basel)
│   │   ├── workflow.py         LangGraph orchestration + builds the fact ledger
│   │   ├── assistant.py        guardrailed AI: "explain" / "ask about this company"
│   │   └── metrics/            deterministic computation (all the numbers)
│   │       ├── profitability.py  solvency.py   liquidity.py   working_capital.py
│   │       ├── saas.py           risk.py       forecast.py    anomaly.py
│   │       ├── dscr.py           debt_service.py   (DSCR ratio + full schedule/stress)
│   │       ├── scorecard.py      memo.py
│   │
│   ├── security/               ── SECURITY CONTROLS (used by all layers) ───────
│   │   ├── config.py           fail-closed secrets, security constants
│   │   ├── sessions.py         revocable server-side JWT sessions
│   │   ├── ratelimit.py        brute-force throttling (MongoDB, TTL)
│   │   ├── mfa.py              TOTP + encrypted secrets
│   │   ├── audit.py            security event log
│   │   ├── passwords.py        server-side password policy
│   │   ├── uploads.py          upload validation (size, magic bytes, zip bomb)
│   │   └── llm_guard.py        prompt-injection screening + output checks
│   │
│   └── shared/                 ── USED EVERYWHERE ─────────────────────────────
│       ├── schema.py           data models (NormalizedCompanyRecord, Fact Ledger)
│       ├── formatting.py       money/period/percent formatting (₹ lakh/crore, $ M/B)
│       ├── currency.py         FX normalization to a base currency
│       ├── meanings.py         one-line plain-English meaning per metric
│       ├── components.py       reusable Streamlit UI components
│       ├── metrics.py          Prometheus metrics (page renders, logins, build info)
│       └── styles.css          the design system
│
├── scripts/                    llm_redteam.py (live injection test), make_admin.py
└── tests/                      266 tests (pytest); tests/security/ = 113 security tests
```

## Execution flow

1. **`app.py`** starts → refuses to run without a strong `JWT_SECRET` → validates the session JWT against the `sessions` collection. Not logged in → **`finveritas/auth/pages.py`**.
2. Logged in → sidebar nav. **Upload** → **`finveritas/ingestion/page.py`** ingests via the
   right module (`pdf/` · `ticker` · `spreadsheet`), scores credibility, then calls
   **`finveritas/analysis/workflow.py`** to run the pipeline.
3. The workflow fills the **fact ledger** using **`finveritas/analysis/metrics/*`**
   (all deterministic), then the AI agents narrate.
4. **Financial Analysis** → **`finveritas/analysis/page.py`** renders the verdict,
   scorecard, DSCR + stress, metrics, anomalies, forecast, AI assistant, and the memo.

**The rule:** everything in `analysis/metrics/` computes numbers deterministically;
`analysis/workflow.py` + `assistant.py` only explain them. `shared/` is used by all layers.

## Run it

```sh
cd PBL-2
source .venv/bin/activate
streamlit run app.py
```
