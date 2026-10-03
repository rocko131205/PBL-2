# FinVeritas — Explainable Credit-Risk Analysis

> **Financial truth, quantified.**
> A credit-underwriting assistant that ingests a company's financials and produces a
> defensible read on **can they repay, how risky, and on what terms** — with every
> number computed deterministically in Python and the LLM used only to *explain*, never
> to calculate.

---

## The one rule

**Python computes every number; the AI only narrates.** Ratios, DSCR, the credit grade,
default-probability bands — all deterministic. The LLM classifies the company, picks peer
tickers (whose data is then *fetched*, not guessed), and turns the computed facts into
plain English. It can never invent or change a figure.

---

## Architecture

The **Fact Ledger** is the contract between the deterministic engines (which compute every
number in Python) and the AI layer (which only narrates). See the full diagram and layer
breakdown in **[ARCHITECTURE.md](ARCHITECTURE.md)**.

For the file tree and execution order, see **[STRUCTURE.md](STRUCTURE.md)**; for how the
system evolved (V1 → V2 → V3), see **[VERSION_HISTORY.md](VERSION_HISTORY.md)**.

---

## What it produces

- **Verdict banner** — one line: grade, risk, min DSCR, biggest watch item.
- **Credit scorecard** — an industry-aware grade (AA…D) + approximate default-probability
  band, with a transparent factor breakdown (repayment, leverage, liquidity, profitability,
  stability).
- **Debt serviceability** — real DSCR with a selectable cash basis (EBITDA / EBIT / OCF /
  **CFADS**), a full year-by-year amortization schedule, **minimum DSCR**, and **stress
  tests** (revenue haircuts, rate shocks).
- **Metrics** — profitability, solvency, liquidity, working-capital cycle (DSO/DIO/DPO/CCC),
  each with a plain-English "what this means".
- **Trends & forecast** — history plus a 3-year projection (base / optimistic / pessimistic).
- **Peer benchmarking** — real peer data fetched from yfinance (never LLM-estimated).
- **Anomaly alerts** — large swings, sign flips, balance-sheet-that-doesn't-tie, impossible values.
- **AI assistant** — "explain these results" + a scoped "ask about this company" chat,
  grounded strictly in the computed facts.
- **Credit Memo** — a one-page lender memo, downloadable and printable to PDF.

---

## Key features

| Area | Details |
|------|---------|
| **3 data sources** | Bloomberg PDF, Yahoo Finance ticker, private CSV/Excel |
| **Deterministic engine** | All metrics + grade + DSCR computed in Python; immutable Fact Ledger |
| **Industry-aware** | SaaS / financial / manufacturing / retail / general scoring profiles |
| **Currency-correct** | FX-normalizable; INR shows in lakh/crore, others in K/M/B/T; reported-unit rescaling |
| **Guardrailed AI** | Any OpenAI-compatible endpoint (Groq, LM Studio, Ollama, OpenAI); explains, never calculates |
| **Security** | bcrypt, TOTP MFA, revocable server-side JWT sessions, lockout, hardened OTP reset, audit log, admin dashboard, prompt-injection guard — see [SECURITY.md](../SECURITY.md) |
| **Tested** | 266 pytest tests (113 security regression tests) + bandit / pip-audit / gitleaks in CI |

---

## Setup

```sh
git clone https://github.com/rocko131205/PBL-2.git
cd PBL-2
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py                                    # open http://localhost:8501
```

### Environment variables (`.env` in the repo root)

```env
# Security — REQUIRED, random, >= 32 chars (the app refuses to start otherwise)
#   python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=
MONGO_URI=mongodb+srv://...

# Email OTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASS=your_app_password

# LLM (any OpenAI-compatible endpoint)
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
LLM_API_KEY=your_key

# Optional supplemental data
NEWSAPI_KEY=...
FMP_API_KEY=...
```

The app runs without the LLM — only the narrative/AI-assistant needs the endpoint; all
numbers work regardless.

---

## Data sources

- **Bloomberg PDF** — upload the income statement and/or balance sheet PDFs; the OCR chain
  extracts them. If the statement is reported "in millions/lakhs/crore", pick that unit on
  the Upload page so magnitudes are correct.
- **Ticker (Yahoo Finance)** — e.g. `INFY.NS`, `TCS.NS`, `AAPL`. Pulls income statement,
  balance sheet, and cash-flow statement automatically.
- **Private CSV/Excel** — columns: `period, revenue, total_assets, total_liabilities,
  current_assets, current_liabilities, equity`. A template is available in the app.

---

## Testing

```sh
pytest                     # 266 tests
pytest tests/security -q   # security regression suite only
```

See [SECURITY.md](../SECURITY.md) for the security assessment, threat model and scanning commands.

---

## Deployment

Every push runs a simple GitHub Actions pipeline: **test** (lint + pytest) → **build** (Docker
image) → **deploy**. Commits to `main` are pushed to GitHub Container Registry and deployed to
Render. See **[CI_CD.md](CI_CD.md)** for the pipeline diagram and the one-time setup.

To self-host on your own Ubuntu server instead, an Ansible playbook installs the packages,
creates the users, and manages the files and services. See
**[CONFIG_MANAGEMENT.md](CONFIG_MANAGEMENT.md)**.

On Kubernetes, the app runs as a 3-replica Deployment behind a Service, with zero-downtime
rolling updates and one-command rollback. See **[KUBERNETES.md](KUBERNETES.md)** for the
manifests and a recorded demonstration.

For monitoring, the app exposes Prometheus metrics, and a Compose stack (Prometheus, Grafana,
blackbox exporter, edge proxy) feeds a dashboard of uptime, latency and error rate. See
**[MONITORING.md](MONITORING.md)**.

---

## Disclaimer

FinVeritas is **decision support for a qualified analyst** — not a loan approval, rejection,
or binding credit decision. It does not compute regulatory capital measures (Basel III LCR,
NSFR, Tier 1/2). All data is from public filings / Yahoo Finance for educational use.

Built as a Problem-Based Learning (PBL) academic project.
