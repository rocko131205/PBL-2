# FinVeritas — Version History (V1 → V2 → V3)

> **Purpose of this file:** a single, plain-language reference for what the project
> looked like at each stage. If you ever ask "what was in V1?" or "what changed in V2?"
> or "what's left for V3?", the answer is here.

---

## Quick summary (read this first)

| Version | One line | State |
|--------|----------|-------|
| **V1** | Original app: 5 agents in a fixed line, LLM allowed to guess numbers | Replaced |
| **V2** | Rebuilt so **Python does all math**, LLM only explains; LangGraph orchestration | **Current, built** |
| **V3** | Repo cleaned + hardened, plus a roadmap of features not yet built | **This cleanup done; roadmap planned** |

**The one idea that defines the project:** *All financial numbers are calculated in
Python. The LLM never does math — it only turns pre-computed numbers into words.*
V1 broke this rule in places; V2 enforces it; V3 protects and extends it.

---

## V1 — The original implementation (past)

**What it was:** A Streamlit app that read financial data from three sources
(Bloomberg PDF, Yahoo Finance ticker, private CSV) and ran it through a **fixed,
linear pipeline of agents**.

**How it worked:**
- Ingest data → score its credibility → run agents one after another → show results.
- The agents were: **Revenue → Balance Sheet → Liquidity → Sentiment → Cross-Reference.**
- An intermediate iteration also had a linear credit flow:
  `check_data → compute_dscr → peer_match → credit_risk → END`.
- The LLM was used both to narrate *and*, in a few places, to produce numbers.

**Where V1 was weak (the reasons V2 exists):**
1. **DSCR used a fake number.** It estimated operating income as `revenue × 0.20` —
   a made-up 20% proxy. This is financially wrong; DSCR must use *actual* operating
   income or EBITDA.
2. **Peer financials were hallucinated.** The LLM was asked to *estimate* competitors'
   revenue and margins. Those numbers were invented, not real.
3. **SaaS metrics used hardcoded assumptions** instead of the company's actual growth.
4. **The pipeline was rigid.** A fixed line of steps — no real "decide what to do next"
   behaviour.
5. **No single source of truth** for computed numbers — logic was spread around.

---

## V2 — The current architecture (built and running)

**What changed in one sentence:** the system was re-architected so that a
**deterministic computation layer** produces every number, and an **agentic reasoning
layer** (LLM) only interprets those numbers — the two can never mix.

### The big new ideas

1. **The Fact Ledger** (`src/schema.py` → `FinancialFactLedger`)
   - A list of computed metrics, each with its value, formula, inputs used, and a
     PASS/WARN/FAIL risk signal.
   - Once computed, these facts are **immutable** — the LLM reads them but cannot change
     them. This is the "contract" between the math and the AI.

2. **Deterministic calculators** (pure Python, no LLM):
   - `profitability_calculator.py` — margins, ROE, ROA, ROCE
   - `solvency_calculator.py` — leverage / debt ratios
   - `liquidity_calculator.py` — current ratio, working capital
   - `revenue_calculator.py` — growth, CAGR
   - `saas_engine.py` — SaaS metrics from *actual* growth (not hardcoded)
   - `dscr_engine.py` — **real DSCR** with a proper numerator hierarchy
     (EBITDA → Operating Income → reconstructed), and it **refuses to guess** when data
     is missing (no more `revenue × 0.20`)
   - `risk_indicator_engine.py` — turns all metrics into an overall risk dashboard

3. **LangGraph agentic workflow** (`src/agent_workflow.py`) — 5 nodes, in order:
   - **Company Intelligence** — LLM classifies the company (industry, country, SaaS type)
   - **Financial Computation** — runs all the deterministic calculators (NO LLM here)
   - **Peer Analysis** — LLM only picks peer *tickers*; real data is then **fetched**
     from Yahoo Finance (not hallucinated)
   - **Qualitative Analysis** — LLM reads any management commentary for context
   - **Credit Assessment** — LLM writes the final narrative from the computed facts only

4. **Final output:** a `CreditAssessmentReport` — a decision-support document for a
   lender (strengths, risks, DSCR, peer comparison, risk level, narrative). It is
   explicitly *not* an approve/reject decision.

### Other things V2 has
- **Three data sources:** Bloomberg PDF (pdfplumber), Yahoo Finance ticker (yfinance),
  private CSV/Excel.
- **Data Credibility Engine** (`data_verifier.py`) — scores each data load 0–100.
- **Authentication:** MongoDB users, bcrypt passwords, JWT sessions, email OTP.
- **UI:** Streamlit, Bloomberg-terminal styling, dark/light themes, methodology
  transparency panels.
- **Tests:** 52 automated tests (see `tests/`), including tests that specifically prove
  the system never fabricates numbers.

### Honest limitations still in V2 (targets for V3)
- **Risk thresholds are SaaS-tuned** and applied to every company — so a bank or airline
  can be flagged incorrectly. Not yet industry-aware.
- **Numbers are shown as text; there are no charts** yet.
- **Two calculators run for the same numbers** (old V1 calculators still run alongside
  the V2 fact ledger "for backward compatibility").
- **The LLM is a small local model** and JSON parsing is fragile.
- **Reports are not saved** — they disappear when the session ends.
- **Sentiment / qualitative analysis is effectively inactive** (no data is fed to it).

---

## V3 — Cleanup done + roadmap

V3 has two parts: (A) the cleanup already completed, and (B) the features planned next.

### (A) Cleanup completed in this pass ✅

1. **Removed the entire virtual environment from git.** `.venv/` (17,724 files) had been
   committed by accident. It is now untracked (still on disk, so the app still runs).
   - **Tracked files dropped from 17,799 → 61.** The repo is now actual project code.
2. **Untracked runtime artifacts:** the `output/` JSON files and all `.DS_Store` files
   were removed from git (they are generated/OS files, not source).
3. **Deleted 4 dead code files** that nothing used anymore:
   - `src/credit_risk_agent.py`, `src/peer_matching_agent.py`,
     `src/sentiment_agent.py` (old V1 agents), and `src/report_generator.py`
     (an unused alternate report builder).
4. **Made the test suite runnable:** added `pytest` to `requirements.txt`.
   **All 52 tests pass.**
5. **Fixed git hygiene:** added a root `.gitignore` and ignored `.pytest_cache/` so the
   accidental commits can't happen again.

*Result: same working app, dramatically cleaner and lighter repository.*

### (B) Revamp build — done on branch `V3-revamp` ✅

Built in tested, committed phases (109 tests passing):

1. **Phase 1 — Data foundation** (`currency.py`, `formatting.py`, schema + ingestion):
   currency normalization to a base currency, readable money (K/M/B/T + symbol,
   fixes "256,345,567M"), cash-flow statement ingestion, data-completeness report.
2. **Phase 2 — Real DSCR engine** (`debt_service.py`): selectable numerator
   (EBITDA/EBIT/OCF/CFADS), full amortization schedule, per-year + **minimum DSCR**,
   **stress testing** (revenue haircuts, rate shocks), coverage ratios. Wired into the UI.
3. **Phase 3 — Credit scorecard** (`credit_scorecard.py`): one industry-aware
   **grade + PD** with a transparent factor breakdown. Fixes the "SaaS thresholds for
   everyone" bug. Wired into the UI.
4. **Phase 4 — Credit Memo** (`credit_memo.py`): one-page lender memo with printable
   HTML export (browser print-to-PDF). Wired into the UI.
5. **Phase 5 — Forecasting + charts** (`forecast.py`): revenue history + 3-year
   projection (base/optimistic/pessimistic) and a margin-trend chart. First real charts.
6. **Phase 6 — Polish**: removed ghost "Sentiment" UI, updated landing text and the
   readiness badges to the real pipeline, moved raw JSON behind a developer toggle.

### (C) Still on the roadmap 🚧

- Remove the duplicate V1 calculators (one source of truth per number).
- Harden the LLM layer (reliable JSON parsing + stronger-model option).
- Persist analyses to MongoDB (history + compare over time).
- Peer percentile positioning + radar chart.
- Further capability agents from the original V2 roadmap:
  Assumption Validation, Anomaly/Alert detection, Working Capital & MPBF,
  Geography-wise impact, Executive/Governance background.

---

## Where things live

All source is under `finveritas/`, grouped by the user journey.
See **[STRUCTURE.md](STRUCTURE.md)** for the full file tree and execution flow.

*Last updated: 2026-09-24 (V3 revamp built on branch `V3-revamp`).*
