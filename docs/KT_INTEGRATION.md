# DeterminX integration

FinVeritas absorbed the features of **DeterminX** (a parallel Streamlit fork, no longer in this repository) by
**porting them into this codebase's own schema and architecture**. DeterminX's Streamlit app is not run or
imported anywhere. This page records what came across, where it lives now, how it differs, and what is still open.

The rule is unchanged: **Python computes every number; the LLM only narrates.** Every new agent decides its
numbers and verdicts in Python first, then asks the model to put only those results into words. The model's output
is checked against the facts it was given (`security/llm_guard.check_output`), and if the model is unreachable the
numbers are still shown.

---

## Status

| Area | State |
|---|---|
| Shelf-company filter, FMP endpoint fix, new statement fields | **Done** |
| Extended deterministic metrics (cost, efficiency, ROIC, cash flow, growth, trends, Tandon, sector) | **Done** |
| Advisory risk checks and own-history z-score monitoring | **Done** |
| Forecast assumption validation, competitive benchmark, working-capital narration | **Done** |
| Geography and governance agents, external data layer | **Done** |
| API endpoints and UI (sidebar navigation, new pages, sector selector) | **Done** |
| vLLM / AMD ROCm / Groq provider selection | **Not done** (see [Not done](#not-done)) |
| DPDP consent gate and tamper-evident audit chain | **Not done** |
| Automated tests for the new code | **Not done** |

---

## Where each DeterminX piece went

| DeterminX | FinVeritas | Notes |
|---|---|---|
| `core/metrics/revenue.py`, `growth.py`, `trends.py` | `analysis/metrics/extended/growth.py` | Revenue/growth CAGR, average YoY, trend labels |
| `core/metrics/cost.py` | `extended/cost.py` | |
| `core/metrics/efficiency.py` | `extended/efficiency.py` | Turnover ratios only. DSO/DIO/DPO/CCC already come from `working_capital.py` |
| `core/metrics/returns.py` | `extended/efficiency.py::compute_returns` | ROIC only. ROE/ROA/ROCE already come from `profitability.py` |
| `core/metrics/cash_flow.py` | `extended/cash_flow.py` | |
| `core/metrics/domain.py` | `extended/domain.py` | SaaS, banking, retail, manufacturing. Rule of 40 stays in `saas.py` |
| `core/metrics/risk.py` | `extended/risk_checks.py` | 6 of its 9 checks. Weak current ratio / interest coverage / DSCR already exist in the core ledger |
| `core/metrics/debt_service.py` | *(not ported)* | Our `dscr.py` and `debt_service.py` are richer (schedules, stress tests) |
| `core/metrics/schema.py`, `util.py`, `engine.py` | `shared/schema.py`, `extended/_util.py`, `extended/engine.py` | Statuses added to `FactStatus`; see below |
| `core/src/risk_monitoring/anomaly_engine.py` | `analysis/metrics/anomaly.py::zscore_scan` | |
| `core/src/forecast/` | `analysis/metrics/forecast.py` (verdict, projection, drivers) and `intelligence/forecast_validation.py` | |
| `core/src/competitive/` | `intelligence/competitive.py` | |
| `core/src/credit/working_capital_agent.py` | `extended/credit.py` (numbers) and `intelligence/credit.py` (narration) | |
| `core/src/geography/geography_agent.py`, `geography_extractor.py` | `intelligence/geography.py` | `scenario_parser.py` (LLM transcription) not ported |
| `core/src/governance/` | `intelligence/governance.py` | Includes DIN extraction |
| `core/src/external/` | `intelligence/external.py` | Macro, news, guidance, plus two "not configured" stubs |
| `core/src/data_verifier.py::_check_shelf_company_indicators` | `ingestion/credibility.py` | Weight 15, always last |
| `core/src/supplemental_fetchers.py` | `ingestion/supplemental.py` | FMP `/stable/` endpoint; inventory, receivables, payables back-fill |
| `core/src/mapper.py`, `yfinance_ingestion.py`, `private_company_ingestion.py` | `ingestion/pdf/labels.py`, `ticker.py`, `spreadsheet.py`, `normalize.py` | New fields: SG&A, R&D, amortization, investing/financing cash flow |

**Deliberately not ported:** the Streamlit app and UI (`core/app.py`, `core/ui/`), the SQLite run log and JSONL audit
chain (`src/db.py`, `src/audit_log.py`), the meta-orchestrator and drift detection (`src/meta_agent.py`), Account
Aggregator ingest (`src/aa_ingestion.py`), the old sentiment agent, the thin `agents/` wrappers, and the standalone
prototypes (`financial_background_check.py`, `Agent/revenue_stability_agent.py`, `qwen2.3.py`). Our engines already
cover what the prototypes did.

---

## Design decisions

**A separate extended ledger.** The new metrics use the same schema (`FactLedgerEntry`) but live in their own
ledger, `state["extended_ledger"]`, with no metric name that also appears in the core ledger. Two existing consumers
would otherwise have changed behaviour: `risk.build_risk_dashboard` turns every ledger risk signal into an input of
the overall risk level (it would have moved existing credit grades), and the credit-assessment and assistant prompts
dump every ledger entry (about 150 more facts could overflow a small local model's context).

**Advisory risk checks.** The six checks in `extended/risk_checks.py` and the z-score scan are reported in their own
"Risk Analysis" page and **never affect the credit grade or the overall risk level**.

**Availability is explicit.** `FactStatus` gained `REQUIRES_ADDITIONAL_DOCUMENT` and `REQUIRES_EXTERNAL_DATA`.
A metric without a number says why, and the UI badges it:

| Status | Meaning |
|---|---|
| `VALID` | Computed from the ingested statements |
| `ESTIMATED` | Computed using a disclosed simplifying assumption (for example Tandon's 25% minimum NWC) |
| `INSUFFICIENT_DATA` | Not enough ingested data |
| `REQUIRES_ADDITIONAL_DOCUMENT` | Needs a document or operational input that isn't in the statements |
| `REQUIRES_EXTERNAL_DATA` | Needs a data source that isn't configured |

Two metrics are structurally never guessed: **Estimated MPBF is always `ESTIMATED`**, and **Drawing Power is always
`REQUIRES_ADDITIONAL_DOCUMENT`** (it needs a bank sanction letter and stock/receivables ageing). There is no code path
that returns a number for Drawing Power.

**Ledger values can be labels.** `FactLedgerEntry.value` accepts text such as `"increasing"` for trend metrics.

**Assistant and memo use a short digest.** `api/report.py::extended_summary` picks about 10 key extended metrics, the
working-capital estimates and any advisory flags (about 3,000 characters in all, not the full 50 entries, so a small
local model's context isn't swamped). The assistant's prompt gets them as grounded lines with estimates labelled, and
the credit memo gets two sections, *Working Capital (Estimate)* and *Advisory Watch Items*, each stating that it
doesn't change the grade. A memo for a company with neither simply omits them.

**Untrusted text is spotlighted.** Pasted filings, segment notes and news headlines reach the model only through
`llm_guard.wrap_untrusted`, never inside the trusted facts. Entity names go through `safe_entity_name`.

---

## What each agent does

| Agent | Deterministic core (Python) | What the LLM does |
|---|---|---|
| **Forecast check** | Reference points (own CAGR and average growth, guidance, a user benchmark) → verdict `ALIGNED / OPTIMISTIC / AGGRESSIVE / CAUTIOUS / OVERLY_CONSERVATIVE` → compound projection | Explains the reasoning; cannot change the verdict or projection |
| **Competitive** | Ten metrics for the company and each peer (peers fetched from Yahoo Finance and run through the same engines), median, mean and gap | Describes the gaps |
| **Working capital** | Tandon Method II: gross working capital, gap, minimum NWC, estimated MPBF, coverage ratio, operating cycle | Explains the position and states the estimate caveats |
| **Geography** | Region revenue, share of total, YoY growth, volatility; a swing of 15% or more is "notable" | Writes a `FACT` section and a hedged `POSSIBLE EXPLANATION` from headlines |
| **Governance** | DIN/director extraction, keyword screen over recent headlines, registry lookup (not configured) | Summarises; a keyword match is always "requires manual verification". Reported separately from financial health |

The ten benchmark metrics are revenue CAGR, EBITDA, EBITDA margin, net profit CAGR, ROE, ROCE, debt to equity, net
margin, gross margin and asset turnover. Absolute EBITDA is only compared between companies reporting in the same
currency.

---

## API

All routes need a signed-in session and (for writes) the CSRF header. Agent calls share the AI assistant's
per-user rate limit, and results are saved on the analysis so a reload shows them.

| Method and path | Purpose |
|---|---|
| `GET /api/sectors` | Sector list and the operational inputs each sector understands |
| `PUT /api/workspace/sector` | Set the sector and its inputs. Applies on the next analysis run |
| `POST /api/analysis/{id}/forecast/validate` | Check a growth assumption |
| `POST /api/analysis/{id}/competitive` | Ten-metric peer benchmark (defaults to the workflow's peers) |
| `POST /api/analysis/{id}/credit/narrate` | Narrate the working-capital assessment |
| `POST /api/analysis/{id}/geography/extract` | Best-effort read of pasted segment-note text, for the user to confirm |
| `POST /api/analysis/{id}/geography` | Analyse regional revenue |
| `POST /api/analysis/{id}/governance/extract` | Best-effort director/DIN extraction from pasted text |
| `POST /api/analysis/{id}/governance` | Run the governance screen |

`GET /api/analysis/{id}` now also returns `extended` (sections, coverage, advisory risks, z-scores, sector),
`intelligence` (saved agent results) and `default_peer_tickers`. Analyses run before this layer existed get the
extended metrics derived on demand from their stored record, so they don't need re-running.

---

## UI

The Analysis report no longer has a horizontal tab bar. **Analysis** in the main sidebar expands into an accordion
(`web/src/layouts/AnalysisNav.tsx`), driven by one tree in `web/src/lib/analysisNav.ts`:

| Group | Pages |
|---|---|
| Overview | |
| Financials | Metrics, Trends, Working Capital, Debt Service |
| Credit | Credit Grade (the Assessment page), Forecast Check, Peers |
| Risk & Alerts | Risk Analysis, Geography, Governance |
| AI Assistant | |
| Reports | Memo, Audit Trail |

The open page is still in the URL (`/analysis?tab=debt`), so refresh, back/forward and shared links work, and a
breadcrumb above the title shows where you are. The Upload page gained an **Industry-specific metrics** card, and the
data-credibility card shows the shelf-company panel (Clear / Caution / High risk).

---

## Configuration

| Variable | Used for |
|---|---|
| `NEWSAPI_KEY` (or `NEWS_API_KEY`) | Headlines for the Geography and Governance agents. Without it they report "not configured" |
| `FMP_API_KEY`, `ALPHA_VANTAGE_API_KEY` | Gap-filling missing balance-sheet fields (now also inventory, receivables, payables) |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | Any OpenAI-compatible endpoint, used for all narration |

The World Bank macro indicator needs no key and is shown only as context, never blended into the forecast verdict.

---

## Known limits

- **z-score sensitivity.** The own-history check needs four periods, and on a short, smooth history even a modest
  move can read as several standard deviations. A flag means "worth a look", not a verdict. The page says so.
- **Regional amounts** are entered in the statements' unit and are not currency-converted.
- **Peers:** the workflow's own peer step wasn't changed (the ten-metric benchmark is a separate button on the Peers page).
- **Not cross-checked** against DeterminX's own TCS example output.
- **Statutory registries** (MCA, SEBI, IBBI) and **analyst estimates** have no data feed in this deployment, as in
  DeterminX, and say so.

## Not done

- **LLM provider selection.** DeterminX's vLLM / AMD ROCm, Groq and Gemini provider defaults, `.env` aliases
  (`vllm`, `vllm-rocm`, `rocm`), the `not-needed` key bypass and `requirements-rocm.txt`. Any OpenAI-compatible server
  already works today by setting the three `LLM_*` variables by hand. Provider settings are still read in three
  places (`api/jobs.py`, `analysis/assistant.py`, `analysis/workflow.py`) and should be centralised.
- **DPDP consent and audit chain.** A consent screen, "delete my data", and a SHA-256-chained audit log with an
  integrity check.
- **Tests** for every module on this page, and `FactStatus` / API coverage.
