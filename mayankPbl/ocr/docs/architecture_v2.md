# FinVeritas V2 — System Architecture & Database Connectivity

## System Architecture Overview

```mermaid
graph TD
    subgraph INPUT["🔹 Raw Data Sources"]
        PDF["📄 Bloomberg PDF Upload<br/>(OCR via Tesseract)"]
        TICKER["📊 Fetch by Ticker<br/>(yfinance API)"]
        CSV["📁 Private Company CSV<br/>(Template Upload)"]
    end

    subgraph EXTRACT["🔹 Extraction & Normalization Layer"]
        OCR["PDF Parser<br/>(pdf_parser.py)"]
        YF["yfinance Ingestion<br/>(yfinance_ingestion.py)"]
        PCI["CSV Loader<br/>(private_company_ingestion.py)"]
        SUPP["Supplemental Fetchers<br/>(FMP / Alpha Vantage)"]
        NORM["Normalized time_series Dict"]
    end

    subgraph ENGINE["🔹 Deterministic Python Metrics Engine"]
        ME["Metrics Engine<br/>(metrics_engine.py)<br/>12 Categories · Pure Python"]
        CRED["Credibility Engine<br/>(data_verifier.py)<br/>8+ Quality Checks"]
    end

    subgraph LEDGER["🔹 Immutable Fact Ledger"]
        FL["Fact Ledger<br/>(fact_ledger.py)<br/>Structured JSON Contract"]
        ANOM["Anomaly Alert System<br/>(anomaly_alerts.py)<br/>PASS / WARN / FAIL"]
    end

    subgraph AGENTS["🔹 Specialized Intelligence Agents"]
        REV["Revenue Agent"]
        LIQ["Liquidity Agent"]
        BS["Balance Sheet Agent"]
        SENT["Sentiment Agent<br/>(VADER + NewsAPI)"]
        CROSS["Cross-Reference Agent"]
    end

    subgraph LLM_LAYER["🔹 LLM Reasoning & Narration"]
        LLM["LLM<br/>(Gemini / GPT / Local)<br/>Explanation ONLY<br/>No Arithmetic"]
    end

    subgraph DB["🔹 Database Layer (MongoDB)"]
        USERS["users Collection<br/>(Auth: login, register, JWT)"]
        HISTORY["file_history Collection<br/>(Per-user analysis history)"]
        CACHE["Session State Cache<br/>(Streamlit st.session_state)"]
    end

    subgraph UI["🔹 V2 User Interface (Streamlit)"]
        UPLOAD["Upload Statement Page"]
        ANALYSIS["Financial Analysis Page"]
        V2INTEL["V2 Intelligence Dashboard<br/>(12-Category Grid + Anomaly Alerts)"]
        WORKFLOW["Agent Workflow Visualization"]
        BASEL["Basel III Alignment"]
        HIST_UI["My File History"]
    end

    PDF --> OCR
    TICKER --> YF
    CSV --> PCI
    OCR --> NORM
    YF --> NORM
    PCI --> NORM
    SUPP --> NORM

    NORM --> ME
    NORM --> CRED
    ME --> FL
    CRED --> FL
    FL --> ANOM

    FL --> REV
    FL --> LIQ
    FL --> BS
    NORM --> SENT
    REV --> CROSS
    LIQ --> CROSS
    BS --> CROSS
    SENT --> CROSS

    REV --> LLM
    LIQ --> LLM
    BS --> LLM
    SENT --> LLM
    CROSS --> LLM

    LLM --> ANALYSIS
    FL --> V2INTEL
    ANOM --> V2INTEL

    UPLOAD --> NORM
    ANALYSIS --> UI
    V2INTEL --> UI
    WORKFLOW --> UI
    BASEL --> UI
    HIST_UI --> UI

    USERS --> DB
    HISTORY --> DB
    CACHE --> DB

    style INPUT fill:#1a1a2e,stroke:#FFB000,color:#E6EDF3
    style EXTRACT fill:#1a1a2e,stroke:#00BFFF,color:#E6EDF3
    style ENGINE fill:#1a1a2e,stroke:#00FF88,color:#E6EDF3
    style LEDGER fill:#1a1a2e,stroke:#CC88FF,color:#E6EDF3
    style AGENTS fill:#1a1a2e,stroke:#FF6B35,color:#E6EDF3
    style LLM_LAYER fill:#1a1a2e,stroke:#FFD700,color:#E6EDF3
    style DB fill:#1a1a2e,stroke:#FF4444,color:#E6EDF3
    style UI fill:#1a1a2e,stroke:#00FF88,color:#E6EDF3
```

## Database Connectivity

### MongoDB Atlas — Document Store

FinVeritas uses **MongoDB** as its primary database for:

| Collection | Purpose | Key Fields |
|---|---|---|
| `users` | Authentication (login, register, password reset) | `user_id`, `email`, `password_hash`, `jwt_token`, `created_at` |
| `file_history` | Per-user analysis history | `user_id`, `entity_name`, `source_type`, `credibility_score`, `fields_loaded`, `timestamp` |

### Connection Flow

```mermaid
sequenceDiagram
    participant User
    participant Streamlit
    participant AuthController
    participant MongoDB
    participant AgentPipeline

    User->>Streamlit: Login (email + password)
    Streamlit->>AuthController: Authenticate
    AuthController->>MongoDB: Query users collection
    MongoDB-->>AuthController: User document (if valid)
    AuthController-->>Streamlit: JWT Token
    Streamlit->>Streamlit: Store in session_state

    User->>Streamlit: Upload PDF / Enter Ticker
    Streamlit->>AgentPipeline: Run analysis
    AgentPipeline-->>Streamlit: Agent outputs + Fact Ledger
    Streamlit->>MongoDB: Insert into file_history
    MongoDB-->>Streamlit: Confirmation

    User->>Streamlit: View "My File History"
    Streamlit->>MongoDB: Query file_history (user_id filter)
    MongoDB-->>Streamlit: Historical analysis records
```

### Session State Architecture

```mermaid
graph LR
    subgraph SESSION["Streamlit Session State"]
        AUTH["auth_user<br/>(JWT + user_id)"]
        OCR_CACHE["ocr_cache<br/>(payload, agent_paths)"]
        AGENT_OUT["agent_outputs<br/>(5 agent results)"]
        V2_LEDGER["v2_fact_ledger<br/>(Immutable JSON)"]
        V2_ANOMALY["v2_anomaly_report<br/>(PASS/WARN/FAIL)"]
        V2_SUMMARY["v2_ledger_summary<br/>(Headlines + Risk)"]
    end

    AUTH --> OCR_CACHE
    OCR_CACHE --> AGENT_OUT
    OCR_CACHE --> V2_LEDGER
    V2_LEDGER --> V2_ANOMALY
    V2_LEDGER --> V2_SUMMARY

    style SESSION fill:#0D1117,stroke:#30363D,color:#E6EDF3
```

## Data Flow — The Immutable Pipeline

The fundamental architecture rule:

> **Python computes → Deterministic Fact Ledger → Specialized Agents → LLM narrates.**
> The LLM must never become the source of truth for financial arithmetic.

```
Input Sources → Extraction → Deterministic Engine → Immutable Ledger → Agents → LLM Narration → UI
     ↓              ↓               ↓                    ↓               ↓          ↓             ↓
  PDF/API/CSV    OCR/Parse     12 Categories          JSON Contract    5 Agents   Explanation   Dashboard
                               Pure Python             Immutable       Read-Only   Only          Rendering
```
