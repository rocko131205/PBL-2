# FinVeritas V2 — Master Implementation Brief

## 0. IMPORTANT: THIS IS AN EVOLUTION OF THE EXISTING PROJECT

You are modifying the **existing FinVeritas V1 codebase**, not creating a new application from scratch.

Before making any changes:

1. Inspect the entire existing repository.
2. Understand the current frontend, backend, database, authentication, PDF/OCR pipeline, financial-data pipeline, agents, prompts, Credibility Engine, dashboards and routing.
3. Identify what is already implemented.
4. Preserve all working V1 functionality.
5. Do NOT rewrite working modules unnecessarily.
6. Extend the existing architecture cleanly.
7. Reuse existing APIs, data models, agents and utilities wherever possible.
8. Do not create duplicate implementations of functionality that already exists.
9. After the audit, map each V2 requirement below to:
   - existing module to modify,
   - new module required,
   - external data dependency,
   - UI change,
   - database/schema change.

The target is:

**V1 = Explainable Historical Financial Analysis**

**V2 = Explainable Financial Intelligence + Forecasting + Risk + Competitive + Governance + Credit + Geography**

The fundamental architecture must remain:

**Python computes → deterministic fact ledger → specialized agents → LLM narrates**

The LLM must never become the source of truth for financial arithmetic.

---

# 1. CORE ARCHITECTURAL CHANGE — DETERMINISTIC FINANCIAL METRICS ENGINE

This is the MOST IMPORTANT V2 change.

V1 currently calculates a limited set of targeted financial ratios.

V2 must introduce a centralized **Deterministic Financial Metrics Engine** that becomes the computational foundation for the rest of the system.

The V2 feasibility analysis establishes approximately 90% coverage of professional financial metrics from the standardized financial data already ingested by FinVeritas.

### Required architecture

Create a centralized Python-side metrics layer.

Conceptually:

```text
Raw Financial Data
        ↓
Data Normalization
        ↓
Deterministic Financial Metrics Engine
        ↓
Immutable / Locked Fact Ledger
        ↓
Specialized Agents
        ↓
LLM Reasoning / Narration
```

The LLM should receive calculated facts, not raw financial statements for performing calculations.

The deterministic engine should produce a structured JSON-like fact ledger containing:

- metric name
- value
- unit
- period
- source
- formula/derivation
- confidence/availability status
- calculation status
- warnings where required

Once generated, these values become the authoritative financial facts used by downstream agents.

---

# 2. EXPAND THE METRICS ENGINE TO 12 CATEGORIES

Implement the following categories.

## 2.1 Revenue Intelligence

Include:

- Revenue
- Net Sales
- Revenue from Operations
- Other Operating Income
- Total Revenue
- Revenue Growth
- CAGR
- YoY Growth

The feasibility report explicitly identifies these as computable from the available financial data.

---

## 2.2 Cost Intelligence

Include:

- Cost of Revenue
- COGS
- Operating Expenses
- SG&A
- R&D Expenses
- Depreciation
- Amortization



---

## 2.3 Profitability Intelligence

Include:

- Gross Profit
- Gross Margin
- EBITDA
- EBITDA Margin
- EBIT
- Operating Profit
- Operating Margin
- PBT
- PAT
- Net Profit Margin
- EPS
- Diluted EPS



---

## 2.4 Liquidity Intelligence

Include:

- Current Ratio
- Quick Ratio
- Cash Ratio
- Working Capital
- Net Working Capital



---

## 2.5 Solvency Intelligence

Include:

- Debt-to-Equity
- Debt-to-Assets
- Equity Ratio
- Financial Leverage
- Interest Coverage
- Net Debt
- Net Debt / EBITDA



---

## 2.6 Debt Servicing Intelligence

Include:

- Interest Coverage Ratio
- DSCR
- Fixed Charge Coverage

BUT:

Do not fabricate precise DSCR when the required debt repayment schedule is unavailable.

The feasibility report explicitly states that precise DSCR requires additional debt maturity/repayment information.

Therefore:

```text
Available data
    ↓
Calculate available debt metrics
    ↓
If debt schedule exists:
    calculate precise DSCR
Else:
    mark DSCR = unavailable / requires additional data
```

Never ask the LLM to estimate a supposedly precise DSCR.

---

## 2.7 Efficiency Intelligence

Include:

- Asset Turnover
- Receivable Turnover
- Payable Turnover
- Inventory Turnover
- Working Capital Turnover
- Fixed Asset Turnover
- Cash Conversion Cycle
- DSO
- DIO
- DPO



---

## 2.8 Return Intelligence

Include:

- ROE
- ROA
- ROCE
- ROIC



---

## 2.9 Cash Flow Intelligence

Include:

- Operating Cash Flow
- Investing Cash Flow
- Financing Cash Flow
- Free Cash Flow
- CAPEX
- Cash Burn
- Operating Cash Flow Ratio



---

## 2.10 Growth Intelligence

Include:

- Revenue Growth
- EBITDA Growth
- PAT Growth
- EBIT Growth
- Asset Growth
- Equity Growth
- Cash Flow Growth
- Multi-Year CAGR



---

## 2.11 Trend Intelligence

Include:

- Revenue Trends
- Profit Trends
- Margin Trends
- Debt Trends
- Cash Flow Trends

These should be calculated from the historical time series rather than generated as LLM observations.

---

## 2.12 Risk Intelligence

Create deterministic risk indicators for:

- Negative EBITDA
- Declining PAT
- Margin Compression
- Rising Debt
- Weak Current Ratio
- Weak Interest Coverage
- Weak DSCR
- Negative Operating Cash Flow
- Abnormal Receivable Growth



The risk engine should produce structured statuses such as:

```text
PASS
WARN
FAIL
```

The classification itself must be deterministic.

The LLM may explain the result but must not change the classification.

---

# 3. FACT LEDGER — NEW CENTRAL CONTRACT

Create a strict internal contract between Python and the agents.

Example conceptual structure:

```json
{
  "metric": "revenue_growth",
  "value": 12.4,
  "unit": "%",
  "period": "FY2026",
  "source": "financial_statement",
  "calculated_by": "deterministic_metrics_engine",
  "status": "VALID"
}
```

The exact schema can be adapted to the existing codebase.

Important rules:

- Agents consume the ledger.
- Agents should not recalculate financial values independently.
- LLM prompts should explicitly state that financial numbers are authoritative facts.
- Narration cannot overwrite facts.
- UI should distinguish calculated facts from AI-generated explanations.

The V2 architecture specifically describes this as a locked/immutable Python fact ledger before specialized agent routing.

---

# 4. FORECASTING — CHANGE FROM HISTORICAL ANALYSIS TO FORWARD-LOOKING ANALYSIS

V2 must add forecasting capability.

The key question changes from:

> What happened?

to:

> What will happen, why, and how confident should we be?



Do not simply add a generic ML prediction model.

The V2 documents specifically emphasize **assumption-driven forecasting with validation**.

---

# 5. ASSUMPTION VALIDATION AGENT

Create a new **Assumption Validation Agent**.

### User flow

User enters an assumption such as:

```text
Expected Revenue Growth = 15%
```

or:

```text
Expected ARR Growth = 15%
```

The system should then obtain relevant reference information such as:

- historical growth
- historical CAGR
- analyst estimates
- industry/sector growth
- competitor performance
- management guidance
- earnings-call expectations
- relevant macroeconomic indicators where available

These are explicitly identified as required forecast-validation inputs.

---

# 6. ASSUMPTION VALIDATION MUST BE DETERMINISTIC

Do NOT allow the LLM to decide whether an assumption is realistic.

Pipeline:

```text
User assumption
       ↓
External/reference data extraction
       ↓
Python normalization
       ↓
Python comparison
       ↓
Deviation calculation
       ↓
Risk/status determination
       ↓
LLM explanation
```

Example:

```text
User assumption = 15%

Management guidance = 8–10%
Historical CAGR = 9%
Sector benchmark = 10%

Python:
15% vs benchmark range
→ significant deviation
→ WARN / AGGRESSIVE ASSUMPTION

LLM:
Explain WHY the assumption appears aggressive.
```

The documents explicitly require the comparison logic to remain deterministic while the LLM explains the discrepancy.

---

# 7. FORECAST OUTPUT MUST INCLUDE "WHY"

Every forecast should have:

1. Forecast value
2. Underlying deterministic calculation
3. Input assumptions
4. Validation result
5. Confidence/risk indicator
6. Explanation

The new Reasoning Layer should explain causal logic rather than merely repeat numbers.

Example:

```text
Revenue growth forecast: 11%

Why:
- historical growth has slowed
- ARPU growth is decelerating
- sector growth is around 9%
- management guidance is 8–10%

Conclusion:
Forecast is moderately above management guidance and should be treated as an optimistic scenario.
```

The LLM is responsible for this explanation, not for changing the forecast number.

---

# 8. COMPETITIVE INTELLIGENCE AGENT

Add a **Competitive Intelligence Agent**.

Purpose:

Move from:

```text
Analyze Company X
```

to:

```text
Analyze Company X
vs
its relevant competitors / sector
```

The agent should compare metrics such as:

- Revenue Growth
- EBITDA
- EBITDA Margin
- PAT Growth
- ROE
- ROCE
- Debt-to-Equity
- margins
- relevant efficiency metrics
- relevant growth metrics

The target company should be positioned against direct peers.

The existing multi-source ingestion architecture should be extended rather than duplicated. The V2 design explicitly identifies Bloomberg/Yahoo Finance/uploads plus competitor data as the intended direction.

---

# 9. PEER BENCHMARKING

Create a deterministic peer comparison layer.

Conceptually:

```text
Target Company
      ↓
Peer Data
      ↓
Normalize metrics
      ↓
Calculate:
  target
  peer median
  peer average
  percentile / gap where appropriate
      ↓
LLM explains competitive position
```

Example:

```text
Company EBITDA Margin = 24%

Sector Median = 19%

Gap = +5 percentage points

LLM:
Explain possible reasons for the superior margin.
```

The underlying numbers must remain Python-generated.

Competitive benchmarking is explicitly identified as an external-data capability.

---

# 10. ANOMALY ALERT SYSTEM

V1's Credibility Engine is primarily a one-time credibility check.

V2 needs an ongoing **Anomaly Alert System**.

Monitor structural ratios such as:

- Debt-to-Equity
- Net Asset / Total Debt
- other leverage/solvency indicators
- historical deviations
- sector deviations

The system should detect:

```text
Current value
vs
historical pattern
vs
sector/reference threshold
```

Then produce:

```text
PASS
WARN
FAIL
```

Example:

```text
Net Asset / Total Debt

Historical range: 3.0–3.5
Current: 2.1

→ WARN
→ Significant deterioration from historical norm
```

The anomaly system is explicitly intended to extend the Credibility Engine from one-time checking into continuous risk monitoring.

Important:

Do not build an unnecessary real-time infrastructure if the existing application does not support scheduled monitoring.

Initially implement the anomaly engine as a reusable monitoring/evaluation service that can run whenever fresh financial data is ingested or analysis is requested.

---

# 11. WORKING CAPITAL & CREDIT INTELLIGENCE AGENT

Add a new **Working Capital & Credit Intelligence Agent**.

This extends FinVeritas from financial analysis into preliminary credit appraisal.

The feasibility report defines the following metrics:

- Gross Working Capital
- Net Working Capital
- Working Capital Requirement
- Working Capital Gap
- Borrower Contribution
- Estimated MPBF
- Current Asset Coverage Ratio
- Estimated Drawing Power
- Operating Cycle
- Inventory Holding Period
- DSO
- DPO
- Cash Conversion Cycle



---

# 12. WORKING CAPITAL CALCULATION

Implement deterministic calculations.

The architecture document gives the following conceptual Tandon Method II flow:

```text
TCA = Total Current Assets

Current Liabilities
        ↓

Working Capital Gap
= TCA - Current Liabilities

Minimum stipulated NWC
= 25% of TCA

Estimated MPBF
= Working Capital Gap - Minimum NWC
```

Keep these calculations in Python.

Do NOT let the LLM calculate them.

---

# 13. IMPORTANT LIMITATION — MPBF MUST BE LABELLED ESTIMATED

Do not claim that the system produces bank-grade MPBF from ordinary financial statements alone.

The feasibility report explicitly says precise MPBF/Drawing Power requires additional information such as:

- existing working-capital limits
- inventory ageing
- receivables ageing
- borrower-specific contribution
- CMA data
- other bank-specific information



Therefore UI must clearly distinguish:

```text
Estimated MPBF
```

from:

```text
Precise / Bank-grade MPBF
```

If required data is missing, show:

```text
Insufficient data for precise calculation.
Estimated value shown using available assumptions.
```

Never silently fabricate missing inputs.

---

# 14. DSCR

Implement DSCR support, but make it data-aware.

Conceptually:

```text
DSCR =
(PAT + Depreciation + Interest)
/
(Principal Repayment + Interest)
```

However, precise calculation requires a debt repayment/maturity schedule.

Therefore:

```text
If debt schedule available:
    calculate DSCR
Else:
    show unavailable
    explain required data
```

Do not invent principal repayment values.

---

# 15. GEOGRAPHY-WISE IMPACT ANALYSIS AGENT

Add a **Geography-wise Impact Analysis Agent**.

This should use geographic revenue information already disclosed in annual reports.

No completely new financial-data source is necessarily required for the basic version; the new requirement is mainly parsing and analysis logic.

Pipeline:

```text
Annual Report
      ↓
Regional revenue extraction
      ↓
Python calculation
      ↓
Region:
  Revenue
  Revenue Share
  YoY Growth
  Volatility
      ↓
News/Sentiment pipeline
      ↓
Regional incident/event matching
      ↓
LLM causal narration
```

Possible regions:

- North America
- Europe
- APAC
- other disclosed regions

---

# 16. GEOGRAPHY ANALYSIS MUST KEEP NUMBERS DETERMINISTIC

Example:

```text
APAC Revenue:
FY2025 = ₹X
FY2026 = ₹Y

YoY Growth = Python calculation

Regional incident:
Supply-chain disruption

LLM:
Narrates whether the incident could plausibly explain the decline.
```

Do NOT let the LLM invent the regional revenue figure.

The documents explicitly state that regional revenue, share, growth and volatility remain Python-computed while the LLM only narrates the likely cause.

Also clearly distinguish:

```text
FACT:
APAC revenue declined 12%.

POSSIBLE EXPLANATION:
Supply-chain disruption may have contributed.
```

Do not present the causal explanation as proven fact unless the data actually establishes it.

---

# 17. EXECUTIVE BACKGROUND / GOVERNANCE AGENT

Add an **Executive Background Check Agent**.

Purpose:

Extend trust analysis beyond financial statements into governance.

The design specifically proposes:

```text
Step 1:
Extract Director Identification Number (DIN)
from uploaded filings.

Step 2:
Use DIN to retrieve statutory information where available.

Potential sources:
- MCA
- SEBI
- IBBI

Step 3:
Create governance findings.

Step 4:
LLM narrates findings alongside the financial credibility assessment.
```

This flow is shown explicitly in the V2 architecture document.

Potential screening dimensions include:

- legal issues
- director disqualification
- prior company failures
- conflicts of interest
- relevant statutory actions
- leadership history

The abstract also explicitly describes legal issues, prior company failures and conflicts of interest as governance red flags.

IMPORTANT:

Build external-data connectors behind an abstraction/interface.

Do not hard-code the application around one scraping implementation.

If a source cannot reliably be queried, show:

```text
Data unavailable
```

rather than generating a result.

---

# 18. GOVERNANCE OUTPUT MUST BE SEPARATE FROM FINANCIAL HEALTH

Do not combine everything into one arbitrary AI score.

Prefer something like:

```text
Financial Credibility
PASS

Governance
WARN

Competitive Position
STRONG

Forecast Assumption
AGGRESSIVE

Risk Monitoring
WARN
```

The V2 architecture specifically emphasizes no-judgment reporting where the financial-health classification is determined by deterministic calculations rather than LLM opinion.

---

# 19. 13-CAPABILITY PIPELINE

The V2 architecture describes the evolution from a 5-agent historical pipeline to a broader 13-capability intelligence pipeline.

Do NOT remove the existing V1 agents.

Instead, conceptually evolve:

```text
Existing V1 capabilities
+
Deterministic Metrics Engine
+
Assumption Validation
+
Reasoning / Why Layer
+
Competitive Intelligence
+
Executive Background Check
+
Anomaly Alert System
+
Working Capital & Credit Intelligence
+
Geography Impact Analysis
```

The exact implementation should map these capabilities onto the existing agent architecture rather than blindly creating 13 independent LLM agents.

Important architectural principle:

**Capability ≠ necessarily separate LLM process.**

Reuse services where appropriate.

---

# 20. UI / PRODUCT CHANGES

Do not simply add everything to the existing dashboard.

The V2 UI should make the new intelligence understandable.

Suggested structure:

## Existing Analysis

Keep current V1 functionality.

## Financial Metrics

New comprehensive metrics dashboard:

```text
Revenue
Cost
Profitability
Liquidity
Solvency
Debt
Efficiency
Returns
Cash Flow
Growth
Trend
Risk
```

Use cards/tables/charts where appropriate.

## Forecast

Add:

- forecast inputs
- user assumptions
- historical reference
- benchmark
- management guidance
- validation result
- forecast
- confidence/risk
- explanation

## Competitive Intelligence

Add:

- target company
- selected peers
- comparison table
- peer median
- metric gaps
- narrative

## Risk & Alerts

Add:

- PASS
- WARN
- FAIL
- anomaly
- affected metric
- current value
- reference value
- explanation

## Credit Intelligence

Add:

- working capital
- WCR
- WCG
- MPBF estimate
- DSO/DPO
- CCC
- operating cycle
- DSCR where available
- missing-data warnings

## Geography

Add:

- regional revenue
- regional share
- YoY growth
- volatility
- event/incident correlation
- narrative

## Governance

Add:

- executives/directors
- DIN where extracted
- statutory findings
- red flags
- source/status
- explanation

---

# 21. DATA AVAILABILITY MUST BE FIRST-CLASS

Every advanced metric should have one of these states:

```text
CALCULATED
ESTIMATED
UNAVAILABLE
REQUIRES_EXTERNAL_DATA
REQUIRES_ADDITIONAL_DOCUMENT
```

This is extremely important.

The feasibility study establishes that:

### Directly computable / highly feasible

- Income Statement
- Balance Sheet
- Cash Flow
- Profitability
- Liquidity
- Solvency
- Returns
- Growth
- Trends

are essentially fully computable from the available standardized statements, while Efficiency and Risk are approximately 95% feasible.

### External-data dependent

- Market valuation
- precise DSCR
- governance intelligence
- competitive benchmarking

require additional data.

Do not hide these limitations.

---

# 22. EXTERNAL DATA LAYER

Create a clean external-data abstraction.

Potential categories:

```text
Market Data Provider
Peer Data Provider
Analyst Estimates Provider
Earnings Call / Transcript Provider
Management Guidance Source
Governance / Statutory Provider
News / Event Provider
Debt Schedule Input
```

Each provider should have:

- adapter/interface
- timeout handling
- failure handling
- source metadata
- timestamp
- cached response where appropriate
- normalization layer

Do not tightly couple business logic directly to one external API.

---

# 23. LLM RESPONSIBILITY — STRICT BOUNDARY

The LLM CAN:

- narrate
- summarize
- explain
- identify causal hypotheses
- explain benchmark gaps
- explain assumption deviations
- produce stakeholder-friendly language

The LLM CANNOT:

- calculate financial metrics
- alter calculated values
- decide PASS/WARN/FAIL
- invent missing financial data
- fabricate peer values
- fabricate governance findings
- fabricate debt schedules
- fabricate analyst estimates
- override the fact ledger

The central V2 principle is that the LLM never performs the underlying financial calculations.

---

# 24. SOURCE TRACEABILITY

Every external finding should ideally retain:

```text
source
source_type
retrieved_at
company
executive / metric / event
raw_reference
normalized_value
```

The user should be able to distinguish:

```text
Financial fact
External fact
Calculated metric
AI interpretation
```

This is essential to preserve FinVeritas' explainability and auditability.

---

# 25. EXPERIMENTAL SCENARIO-SHOCK ENGINE — DO NOT MAKE THIS A CORE FEATURE YET

The V2 abstract mentions a possible scenario-shock engine such as:

```text
What if a recession reduces consumer spending by 10% in Year 3?
```

But it explicitly marks this as experimental and pending validation of deterministic re-running of driver models.

Therefore:

**Do not make scenario shock a mandatory V2 implementation unless the existing forecasting architecture can support it deterministically.**

Treat it as:

```text
OPTIONAL / EXPERIMENTAL
```

not as a core acceptance criterion.

---

# 26. WHAT SHOULD NOT CHANGE

Preserve the existing:

- authentication
- user management
- existing PDF upload
- OCR
- financial extraction
- existing financial APIs
- MongoDB/database structure unless extension is necessary
- existing Credibility Engine
- existing V1 agents
- existing report generation
- existing deployment configuration
- existing working UI flows

Only modify them when V2 genuinely requires an extension.

---

# 27. RECOMMENDED IMPLEMENTATION ORDER

Do NOT implement all agents simultaneously.

Implement in this order.

## PHASE 1 — Architecture Audit

First inspect the existing repository and produce:

```text
Existing architecture
Existing agents
Existing APIs
Existing database models
Existing calculation logic
Existing UI routes
Existing authentication
Existing extraction pipeline
```

Then identify exact files that must change.

Do not code yet.

---

## PHASE 2 — Deterministic Metrics Engine

Build:

```text
metrics/
    revenue
    cost
    profitability
    liquidity
    solvency
    debt
    efficiency
    returns
    cash_flow
    growth
    trends
    risk
```

Then create the fact ledger.

This is the foundation for everything else.

---

## PHASE 3 — Regression Testing

Run the V1 system and verify that:

```text
V1 output before V2
=
V1 output after V2
```

where functionality has not intentionally changed.

Then validate the new metrics against known examples / manually verified calculations.

---

## PHASE 4 — Forecast + Assumption Validation

Implement:

```text
Forecast input
→ assumption validation
→ deterministic comparison
→ forecast
→ reasoning/narration
```

---

## PHASE 5 — Competitive Intelligence

Add:

```text
peer selection
→ peer data ingestion
→ normalization
→ deterministic benchmarking
→ LLM explanation
```

---

## PHASE 6 — Risk Monitoring

Add:

```text
historical ratios
→ thresholds / benchmarks
→ anomaly detection
→ PASS/WARN/FAIL
→ explanation
```

---

## PHASE 7 — Working Capital / Credit

Implement:

```text
working capital metrics
→ WCR
→ WCG
→ estimated MPBF
→ DSO/DPO/CCC
→ DSCR when debt schedule exists
```

---

## PHASE 8 — Geography

Implement:

```text
regional extraction
→ regional metrics
→ news/event matching
→ causal narrative
```

---

## PHASE 9 — Governance

Implement:

```text
DIN extraction
→ external statutory lookup abstraction
→ governance findings
→ governance narration
```

---

## PHASE 10 — UI Integration

Only after backend calculations and contracts are stable, integrate the V2 dashboard.

---

# 28. ACCEPTANCE CRITERIA

V2 should NOT be considered complete merely because the UI contains new tabs.

The following must be true.

### Deterministic computation

- All supported financial metrics are calculated in Python.
- No LLM arithmetic is used.
- Metrics originate from the fact ledger.
- Missing data is explicitly handled.

### Forecasting

- User assumptions can be entered.
- Assumptions are compared against available references.
- Comparison math is deterministic.
- Forecast explanations are generated separately.

### Competitive

- Target company can be compared with peers.
- Peer calculations are deterministic.
- Missing peer data is clearly indicated.

### Risk

- Structural financial anomalies can be detected.
- PASS/WARN/FAIL is deterministic.
- Historical/benchmark deviations are visible.

### Credit

- Working capital analysis works with available statements.
- MPBF is clearly labelled estimated where appropriate.
- Precise MPBF does not pretend to exist without required data.
- DSCR is only calculated precisely when required debt information exists.

### Geography

- Regional revenue can be extracted where disclosed.
- Regional share/growth/volatility are Python calculations.
- News/events are used for explanation, not for changing financial facts.

### Governance

- Executive/director information can be extracted where possible.
- External-source results are traceable.
- No unsupported governance accusation is generated.

### Architecture

The final pipeline should effectively be:

```text
                ┌──────────────────────┐
                │   Raw Data Sources   │
                │ PDFs / APIs / Uploads │
                └──────────┬───────────┘
                           ↓
                ┌──────────────────────┐
                │ Extraction / Normalize│
                └──────────┬───────────┘
                           ↓
                ┌──────────────────────┐
                │ Deterministic Python │
                │   Metrics Engine     │
                └──────────┬───────────┘
                           ↓
                ┌──────────────────────┐
                │ Immutable Fact Ledger│
                └──────────┬───────────┘
                           ↓
        ┌──────────────────┼──────────────────┐
        ↓                  ↓                  ↓
 Forecast             Competitive         Risk /
 Validation           Intelligence        Anomaly
        ↓                  ↓                  ↓
        └──────────────────┼──────────────────┘
                           ↓
        ┌──────────────────┼──────────────────┐
        ↓                  ↓                  ↓
   Geography          Credit/Working      Governance
    Analysis             Capital           Intelligence
        └──────────────────┼──────────────────┘
                           ↓
                ┌──────────────────────┐
                │   LLM Reasoning      │
                │   & Narration        │
                └──────────┬───────────┘
                           ↓
                ┌──────────────────────┐
                │   V2 User Interface  │
                └──────────────────────┘
```

---

# 29. FINAL INSTRUCTION TO ANTIGRAVITY

Do not interpret this as permission to redesign the entire project.

Your job is:

**Inspect → Map → Extend → Test → Integrate**

not:

**Rewrite → Replace → Guess**

Before implementing each capability, verify whether the existing code already has part of it.

For every new capability, answer internally:

```text
1. What already exists?
2. What exact V2 requirement is missing?
3. Which existing module should be extended?
4. What new data is required?
5. Which values must be calculated in Python?
6. Which parts can be handled by the LLM?
7. What happens when data is unavailable?
8. How will the result be exposed in the existing UI?
9. How will it be tested?
```

The highest-priority architectural rule is:

> **No financial number generated by the LLM can become an authoritative FinVeritas fact.**

Python remains the source of truth; the LLM is the explanation layer.

The final V2 system should therefore feel like a natural evolution of FinVeritas V1 rather than a separate application bolted onto it.