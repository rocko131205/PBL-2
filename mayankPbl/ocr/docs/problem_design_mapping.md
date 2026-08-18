# FinVeritas V2 — Problem-to-Design Mapping

## Gap Analysis: V1 → V2 Requirements

This document maps every V2 requirement to its identified gap in V1, the corresponding design component, and the implementation file.

### Legend

| Symbol | Meaning |
|---|---|
| ✅ | Fully implemented in V1 |
| 🟡 | Partially implemented — needs extension |
| ❌ | Not in V1 — new implementation |

---

## Core Architecture

| V2 Requirement | Brief §  | V1 Status | Gap Description | V2 Design Component | Implementation File |
|---|---|---|---|---|---|
| Deterministic Metrics Engine (12 categories) | §1–§2 | 🟡 | Only ~3 categories scattered across individual agents | Centralized `compute_all_metrics()` engine | `src/metrics_engine.py` |
| Immutable Fact Ledger | §3 | ❌ | No shared data contract between agents | `build_fact_ledger()` — structured JSON contract | `src/fact_ledger.py` |
| Source Traceability | §24 | ❌ | No metadata tracking (source, retrieved_at, type) | `source_metadata` block in fact ledger | `src/fact_ledger.py` |
| External Data Abstraction Layer | §22 | 🟡 | FMP/Alpha Vantage are direct calls in `supplemental_fetchers.py` | Provider interface pattern in supplemental fetchers | `src/supplemental_fetchers.py` (extend) |
| Anomaly Alert System | §10 | ❌ | Credibility Engine is one-time data quality check | `run_anomaly_detection()` — ongoing structural monitoring | `src/anomaly_alerts.py` |

## Agent-Level Mapping

| V2 Requirement | Brief § | V1 Status | Gap Description | V2 Design Component | Implementation File |
|---|---|---|---|---|---|
| Revenue Intelligence | §1 | 🟡 | Basic revenue/CAGR/YoY exists | Extended in Metrics Engine — adds volatility, trend depth | `src/metrics_engine.py` |
| Cost Intelligence | §1 | ❌ | No COGS, SG&A, R&D, depreciation tracking | New category in Metrics Engine | `src/metrics_engine.py` |
| Profitability Intelligence | §1 | ❌ | No EBITDA, EBIT, margins, EPS | New category — Gross/EBITDA/Net margins + EPS | `src/metrics_engine.py` |
| Liquidity Intelligence | §1 | 🟡 | Current/Quick ratio exist | Extended — adds Cash Ratio, Working Capital trend | `src/metrics_engine.py` |
| Solvency Intelligence | §1 | 🟡 | D/E exists in Balance Sheet Agent | Extended — adds Debt/Assets, Interest Coverage, Equity Ratio | `src/metrics_engine.py` |
| Debt Servicing Intelligence | §11–§14 | ❌ | No DSCR calculations | New — DSCR estimated from EBITDA/Interest Expense | `src/metrics_engine.py` |
| Efficiency Intelligence | §1 | ❌ | No turnover ratios, DSO/DIO/DPO, CCC | New category — full working capital cycle metrics | `src/metrics_engine.py` |
| Return Intelligence | §1 | ❌ | No ROE, ROA, ROCE, ROIC | New category — all return metrics | `src/metrics_engine.py` |
| Cash Flow Intelligence | §1 | ❌ | No OCF, FCF, CFO/Revenue | New category — operating + free cash flow | `src/metrics_engine.py` |
| Growth Intelligence | §1 | 🟡 | Revenue growth only | Extended — Net Income, Total Assets, Equity growth | `src/metrics_engine.py` |
| Trend Intelligence | §1 | 🟡 | Revenue trend only | Extended — multi-metric trend analysis | `src/metrics_engine.py` |
| Risk Intelligence | §10 | ❌ | No deterministic PASS/WARN/FAIL risk flags | New — threshold-based deterministic flags | `src/metrics_engine.py` + `src/anomaly_alerts.py` |

## Future V2 Capabilities (Planned)

| V2 Requirement | Brief § | V1 Status | V2 Design Component | Target File |
|---|---|---|---|---|
| Forecasting + Assumption Validation | §4–§7 | ❌ | `AssumptionValidationAgent` | `agents/assumption_agent.py` |
| Competitive Intelligence | §8–§9 | ❌ | `CompetitiveIntelAgent` | `agents/competitive_agent.py` |
| Working Capital & Credit (MPBF) | §11–§14 | ❌ | `WorkingCapitalAgent` | `agents/working_capital_agent.py` |
| Geography Impact | §15–§16 | ❌ | `GeographyImpactAgent` | `agents/geography_agent.py` |
| Governance / Executive Background | §17–§18 | ❌ | `GovernanceAgent` | `agents/governance_agent.py` |

## Existing V1 Components (Preserved)

| Component | Status | File |
|---|---|---|
| PDF Upload + OCR | ✅ Preserved | `ocr/pdf_parser.py` |
| Ticker Fetch (yfinance) | ✅ Preserved | `src/yfinance_ingestion.py` |
| Private Company CSV | ✅ Preserved | `src/private_company_ingestion.py` |
| Revenue Agent | ✅ Preserved | `src/revenue_agent.py` → `agents/revenue_agent.py` |
| Liquidity Agent | ✅ Preserved | `src/liquidity_agent.py` → `agents/liquidity_agent.py` |
| Balance Sheet Agent | ✅ Preserved | `src/balance_sheet_agent.py` → `agents/balance_sheet_agent.py` |
| Sentiment Agent | ✅ Preserved | `src/sentiment_agent.py` → `agents/sentiment_agent.py` |
| Cross-Reference Agent | ✅ Preserved | `agents/cross_reference_agent.py` |
| Credibility Engine | ✅ Preserved | `src/data_verifier.py` |
| Auth System | ✅ Preserved | `auth/` (login, register, JWT, MongoDB) |
| Analysis History | ✅ Preserved | `auth/db.py` + `auth/ui_pages.py` |
| Streamlit Dashboard | ✅ Preserved | `app.py` + `ui/dashboard_components.py` |
