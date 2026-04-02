# Explainable Financial Analysis System

A Bloomberg Terminal-style Streamlit dashboard that ingests Bloomberg-exported financial statement PDFs, extracts structured time-series data via OCR, computes financial metrics deterministically in Python, and uses a local LLM **only** to generate plain-English explanations of those pre-computed metrics.

> **Core principle:** All financial calculations are done in Python (pandas/numpy). The LLM never sees raw data or computes numbers — it only narrates pre-computed metrics.

---

## What It Does

1. You upload Bloomberg Income Statement and Balance Sheet PDFs
2. The OCR pipeline extracts and structures the data into JSON
3. Five specialized agents compute financial metrics and generate explanations
4. Results are displayed in a Bloomberg-inspired dark-theme dashboard

---

## Agent Pipeline

```
Bloomberg PDFs
    → OCR Parser (pdfplumber)
         → Revenue Agent      — YoY growth, CAGR, volatility, trend
         → Balance Sheet Agent — leverage ratio, growth rates, risk level
         → Liquidity Agent    — current ratio, working capital trend, risk flag
         → Sentiment Agent    — keyword-based news sentiment (optional, needs NewsAPI key)
              ↓
         → Cross Reference Agent — integrated LLM narrative (uses only pre-computed metrics)
              ↓
         Explainable Output
```

Each agent follows the same pattern:
- **Deterministic Python computation** (metrics, risk flags, trends)
- **LLM explanation only** — receives only the metric dict, not raw data; `temperature=0`

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Dashboard | Streamlit |
| PDF Extraction | pdfplumber |
| Data Processing | pandas, numpy |
| LLM Integration | LangChain (`langchain-openai`) |
| LLM (default) | Any OpenAI-compatible endpoint (default: local LM Studio) |
| Pipeline Graph | streamlit-agraph |
| News Sentiment | NewsAPI (free tier) |

---

## Setup

```sh
cd ocr
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Run

```sh
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

---

## LLM Configuration

Configure in the sidebar at runtime. Defaults point to a local LM Studio instance:

| Setting | Default |
|---------|---------|
| Base URL | `http://127.0.0.1:1234/v1` |
| Model | `qwen2.5-coder-1.5b-instruct-mlx` |
| API Key | `local` |

Any OpenAI-compatible endpoint works — swap in GPT-4, Claude via OpenRouter, Ollama, etc.

---

## Sentiment Agent (Optional)

Requires a free [NewsAPI](https://newsapi.org/register) key. Without it, the Sentiment Agent is gracefully skipped and the other four agents run normally. Add your key in the sidebar under **News Settings**.

Sentiment scoring is **keyword-based** (no ML model) — two curated frozensets of ~50 positive and ~50 negative financial terms are matched against each headline.

---

## Dashboard Pages

| Page | Description |
|------|-------------|
| **Upload Statement** | PDF upload, OCR, metric preview cards, Run button |
| **Agent Workflow** | Interactive pipeline diagram with hover tooltips showing live agent outputs |
| **Financial Analysis** | Full metrics + LLM explanation per agent, raw JSON audit trail |
| **Basel III Alignment** | Regulatory context — how the system maps to Pillar 2/3 frameworks |

---

## Output JSON Schema

Every OCR output file follows this schema:

```json
{
  "entity": {
    "entity_id": "COMPANY_NAME",
    "source": "bloomberg",
    "currency": "INR",
    "source_files": ["file.pdf"]
  },
  "time_series": {
    "revenue": [{"period": "2022-FY", "value": 120000}, ...],
    "total_assets": [...],
    "equity": [...],
    ...
  }
}
```

Period format is always `YYYY-FY` (annual) or `YYYY-QN` (quarterly). The OCR parser normalises all Bloomberg header variants automatically.

---

## Agent Validation Rules

- Minimum **4 aligned periods** required for all agents
- No negative values allowed for balance-sheet fields
- Revenue agent enforces chronological ordering and rejects nulls/NaNs
- Liquidity Agent has a built-in compliance retry — if the LLM uses forbidden terms (e.g. "cash flow", "margin"), it retries once with a correction prompt

---

## Project Structure

```
ocr/
├── app.py                    # Streamlit app (4 pages)
├── requirements.txt
├── agents/
│   ├── revenue_agent.py      # Thin wrapper → src/
│   ├── balance_sheet_agent.py
│   ├── liquidity_agent.py
│   ├── sentiment_agent.py
│   └── cross_reference_agent.py
├── src/
│   ├── extractor.py          # pdfplumber → PDFContent
│   ├── parser.py             # PDFContent → ParsedStatement
│   ├── mapper.py             # Bloomberg label → canonical key
│   ├── builder.py            # ParsedStatement[] → company JSON
│   ├── main.py               # CLI entry point
│   ├── revenue_agent.py      # Full agent implementation
│   ├── balance_sheet_agent.py
│   ├── liquidity_agent.py
│   └── sentiment_agent.py
├── ocr/
│   └── pdf_parser.py         # Streamlit-facing OCR wrapper
├── ui/
│   └── dashboard_components.py
├── input_pdfs/               # Drop PDFs here for CLI mode
└── output/                   # Agent JSON outputs written here
```

---

## CLI Mode (no UI)

```sh
# Scan input_pdfs/ and write to output/
python3 -m src.main

# Custom directories
python3 -m src.main --input path/to/pdfs --output path/to/output

# Verbose logging
python3 -m src.main --verbose
```

---

## Basel III Note

This system is **not** a regulatory reporting tool. It does not compute capital adequacy ratios, Tier 1/2 buffers, LCR, NSFR, or any binding Basel III measures. It is intended for:
- Structured financial statement review
- Preliminary credit background checks from public filings
- Risk trend monitoring across reporting periods
- Generation of explainable, auditable financial summaries
