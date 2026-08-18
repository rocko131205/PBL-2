# FinVeritas V2 — Tool & Technology Justification

## Core Architecture Decision

> **Python computes → Immutable Fact Ledger → Specialized Agents → LLM narrates.**

Every technology choice is driven by this principle: **deterministic financial arithmetic must never depend on a probabilistic model**.

---

## Technology Stack Justification

### 1. Python (pandas / numpy) — Deterministic Computation

| Aspect | Justification |
|---|---|
| **Why** | Financial metrics (ratios, growth rates, CAGR, DSCR) require exact, reproducible arithmetic |
| **Why not Excel/R** | Python offers programmatic integration with the full pipeline; pandas handles multi-period time series natively |
| **Alternative considered** | SQL-based computation — rejected because financial formulas involve conditional logic (negative equity edge cases, division-by-zero guards) that are cleaner in Python |
| **Key benefit** | Every metric is auditable — the same input always produces the same output. No randomness, no temperature, no prompt sensitivity |

**Usage in FinVeritas:**
- `src/metrics_engine.py` — 12-category deterministic metrics engine
- `src/data_verifier.py` — 8+ credibility checks (accounting identity, freshness, plausibility)
- All 5 agents compute metrics in Python before invoking the LLM

---

### 2. LLM (Gemini / GPT / Local via LM Studio) — Narration Only

| Aspect | Justification |
|---|---|
| **Why** | Financial analysis needs human-readable explanations; raw numbers alone are insufficient for decision-makers |
| **Why not LLM for computation** | LLMs hallucinate arithmetic (e.g., incorrectly computing CAGR or ratio conversions). Our architecture explicitly prohibits LLM-generated financial numbers |
| **How we enforce this** | Agents pass pre-computed metrics to the LLM via structured prompts. The system message explicitly states: "Do NOT calculate, estimate, or infer any new numbers" |
| **Flexibility** | Supports any OpenAI-compatible endpoint (cloud GPT, self-hosted LM Studio, Gemini) via `base_url` + `api_key` |

**Architectural Guarantee:**
```
Python Metrics Engine → Fact Ledger (immutable) → LLM (read-only access to facts) → Explanation
```
The LLM can never write back to the Fact Ledger.

---

### 3. MongoDB — Document-Oriented Database

| Aspect | Justification |
|---|---|
| **Why document store** | Financial statements vary by company — different line items, different periods, different reporting standards. A rigid relational schema would require constant migration |
| **Why not PostgreSQL** | The data is inherently semi-structured (JSON payloads from OCR/APIs). MongoDB stores these natively without ORM overhead |
| **Why not SQLite** | Need multi-user support (auth system) and cloud deployment capability (MongoDB Atlas) |
| **Collections** | `users` (auth, JWT tokens) and `file_history` (per-user analysis audit trail) |

**Usage in FinVeritas:**
- `auth/db.py` — MongoDB connection, user CRUD, history storage
- `auth/auth_controller.py` — JWT-based authentication against MongoDB
- Analysis history with credibility scores stored per user

---

### 4. Streamlit — Rapid Dashboard Prototyping

| Aspect | Justification |
|---|---|
| **Why** | Bloomberg-terminal-styled financial dashboard with minimal frontend code; session state management for multi-step analysis workflows |
| **Why not React/Next.js** | The project is a financial analysis tool, not a consumer web app. Streamlit's `st.session_state` directly maps to our pipeline: upload → analyze → view results |
| **Why not Dash (Plotly)** | Streamlit's component ecosystem (agraph for workflow visualization, native JSON rendering, expanders for raw data) better fits our needs |
| **Key benefit** | Single `app.py` handles all pages, routing, auth, and agent execution — easy to understand and maintain |

---

### 5. Tesseract OCR — PDF Text Extraction

| Aspect | Justification |
|---|---|
| **Why** | Bloomberg financial statements are multi-page PDFs with tabular data; need reliable text/number extraction |
| **Why not cloud OCR (Google Vision / AWS Textract)** | Cost and data privacy — financial statements contain sensitive corporate data. Local Tesseract keeps data on-premise |
| **Why not raw pdfplumber/PyMuPDF alone** | Bloomberg PDFs have complex layouts (multi-column, nested tables). Our OCR pipeline combines pdf parsing with LLM-assisted field extraction for robust results |

---

### 6. VADER + NewsAPI — Deterministic Sentiment

| Aspect | Justification |
|---|---|
| **Why VADER** | Produces a deterministic compound score (-1 to +1) for each headline. No LLM involvement in the sentiment number |
| **Why not LLM-based sentiment** | LLM sentiment is non-deterministic — the same headline can get different scores on different runs. VADER always returns the same score |
| **Why NewsAPI** | Structured API for fetching recent news by company name. Free tier sufficient for academic use |
| **How it fits** | VADER scores are computed in Python → stored in agent output → LLM explains what the scores mean |

---

### 7. yfinance — Public Company Data

| Aspect | Justification |
|---|---|
| **Why** | Free, reliable API for listed company financial statements (income statement, balance sheet, cash flow) |
| **Why not Bloomberg API** | Cost prohibitive for academic projects; yfinance provides the same fundamental data for free |
| **Supplement** | FMP (Financial Modeling Prep) and Alpha Vantage used as gap-fillers for missing fields via `supplemental_fetchers.py` |

---

### 8. Immutable Fact Ledger Pattern — Architectural Guarantee

| Aspect | Justification |
|---|---|
| **Why** | Prevents the LLM from overriding Python-computed values — the single most important architectural constraint |
| **How** | The fact ledger is a JSON document generated once per analysis run. All downstream agents and the LLM read FROM it; nothing writes TO it |
| **What it contains** | All 12 metric categories, risk flags, source traceability metadata, computation timestamp |
| **Audit trail** | Every fact in the system can be traced back to its source (PDF page, API endpoint, CSV row) and its computation method (Python formula) |

---

## Summary Matrix

| Component | Technology | Primary Role | LLM Involved? |
|---|---|---|---|
| Metrics computation | Python (pandas/numpy) | Deterministic arithmetic | ❌ No |
| Data storage | MongoDB | User auth + analysis history | ❌ No |
| Sentiment scoring | VADER | Compound sentiment score | ❌ No |
| PDF extraction | Tesseract OCR | Text/number extraction | ❌ No |
| Public data fetch | yfinance + FMP + AV | Financial statement retrieval | ❌ No |
| Fact Ledger | JSON (Python-generated) | Immutable data contract | ❌ No |
| Anomaly detection | Python (threshold-based) | PASS/WARN/FAIL flags | ❌ No |
| Narration/Explanation | LLM (Gemini/GPT) | Human-readable analysis | ✅ Yes (explanation only) |
| Dashboard | Streamlit | User interface | ❌ No |

> **Key takeaway:** The LLM is involved in exactly ONE step — generating human-readable explanations of pre-computed facts. All financial numbers, ratios, flags, and alerts are 100% Python-computed and deterministic.
