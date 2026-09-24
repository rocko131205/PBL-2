# Project Structure (flow-based)

Code is grouped by the **user journey**, in execution order. Python package names
can't start with a digit, so folders aren't numbered — the order below is the flow.

```
ocr/
├── app.py                     ← ENTRY POINT / router (auth gate, sidebar nav, dispatch)
│
├── auth/                      ── 1. LOGIN / SIGNUP (runs first) ──────────────
│   ├── ui_pages.py            login, register, forgot-password, history pages
│   ├── auth_controller.py     JWT create/verify, password hashing, OTP
│   ├── db.py                  MongoDB users + file history
│   └── indian_states.py       state/city dropdown data for signup
│
├── ingestion/                 ── 2. GET DATA IN (after login, the Upload page) ─
│   ├── upload_page.py         THE UPLOAD PAGE (PDF / ticker / CSV tabs) + helpers
│   ├── yfinance_ingestion.py  fetch listed-company financials by ticker
│   ├── private_company_ingestion.py   CSV/Excel loader + template
│   ├── supplemental_fetchers.py       FMP / Alpha Vantage gap-fill
│   ├── data_verifier.py       credibility scoring (0–100)
│   ├── payload_mapper.py      raw payload → NormalizedCompanyRecord
│   ├── scale_detection.py     detect "in millions/lakhs/crore" & rescale
│   └── pdf/                    Bloomberg-PDF OCR chain (runs in this order)
│       ├── extractor.py       pdfplumber → PDFContent
│       ├── parser.py          PDFContent → ParsedStatement
│       ├── mapper.py          Bloomberg label → canonical field
│       ├── builder.py         statements → company JSON
│       ├── pdf_parser.py      Streamlit-facing wrapper
│       └── main.py            CLI entry (python3 -m ingestion.pdf.main)
│
├── analysis/                  ── 3. ANALYSE & PRESENT (the results) ───────────
│   ├── analysis_page.py       Agent Workflow, Financial Analysis (all V3
│   │                          sections), and Basel pages
│   ├── agents/                the LLM layer (reasoning only, never math)
│   │   ├── agent_workflow.py  LangGraph orchestration + the fact ledger build
│   │   └── ai_assistant.py    guardrailed "explain" / "ask about this company"
│   └── engines/               deterministic computation (all numbers)
│       ├── profitability_calculator.py   solvency_calculator.py
│       ├── liquidity_metrics.py          working_capital.py
│       ├── saas_engine.py                risk_indicator_engine.py
│       ├── dscr_engine.py                debt_service.py   (DSCR + stress)
│       ├── credit_scorecard.py           credit_memo.py
│       ├── anomaly_engine.py             forecast.py
│
├── shared/                    ── USED EVERYWHERE ──────────────────────────────
│   ├── schema.py              the data models (NormalizedCompanyRecord, Fact Ledger)
│   ├── formatting.py          money/period/percent formatting (₹ lakh/crore, $ M/B)
│   ├── currency.py            FX normalization to a base currency
│   ├── metric_meanings.py     one-line plain-English meaning per metric
│   ├── components.py          reusable Streamlit UI components (was ui/)
│   └── styles.css             the design system
│
└── tests/                     153 tests (pytest)
```

## Execution flow

1. **`app.py`** starts → checks the JWT. Not logged in → **`auth/ui_pages.py`** (login/signup).
2. Logged in → sidebar nav. **Upload** → **`ingestion/upload_page.py`** ingests via the
   right ingestion module (pdf / yfinance / csv), scores credibility, and calls
   **`analysis/agents/agent_workflow.py`** to run the pipeline.
3. The workflow fills the **fact ledger** using **`analysis/engines/*`** (all deterministic),
   then the LLM agents narrate.
4. **Financial Analysis** → **`analysis/analysis_page.py`** renders the verdict, scorecard,
   DSCR, metrics, anomalies, forecast, AI assistant, and the downloadable memo.

**The rule:** everything in `analysis/engines/` computes numbers deterministically;
`analysis/agents/` only explains them. `shared/` is imported by all layers.
