# FinVeritas — New UI (`ui-enhancement` branch)

This branch replaces the Streamlit interface with a **React frontend** served by a **FastAPI backend**.
The analysis logic is unchanged: every metric, the credit grade and the DSCR are still computed
deterministically in Python, and the AI only narrates. What changed is how the app is delivered and what it
looks like.

> **Status:** feature parity is reached for every screen of the old app. The Streamlit app (`app.py`) is still
> in the repo and still works; it has **not** been removed yet. Deployment, CI and the Dockerfile still target
> Streamlit. See [What's left](#whats-left).

---

## Why

Streamlit reran the whole script on every click, built navigation from radio buttons, and needed 465 lines of CSS
overrides to look acceptable. The new UI gives instant navigation, real routing, proper charts and tables, and a
design that doesn't fight the framework.

## Architecture

```
web/  (React + TypeScript)  ──  /api/*  ──►  api/  (FastAPI)  ──►  finveritas/  (unchanged domain code)  ──►  MongoDB
```

- **One deployable.** In production FastAPI serves the built React app (`web/dist`) and the API from the same
  origin, so there is no CORS and no second service.
- **`finveritas/` is reused as-is.** The metrics, ingestion, credibility checks, LangGraph workflow, LLM guard and
  security modules have no Streamlit dependency, so the API only wraps them. A few small edits were needed (listed
  [below](#changes-to-existing-code)).
- **Per-user state moved server-side.** What Streamlit kept in `st.session_state` (the loaded dataset, scale,
  analysis) now lives in MongoDB, keyed by user id.

## What was built

### Screens

| Route | What it does |
|---|---|
| `/login`, `/register`, `/forgot` | Sign in (with a second step for 2FA), register with a state→city cascade and a live password checklist, and a 3-step email-code password reset. |
| `/upload` | Three data sources: **Bloomberg PDF** (drag-and-drop, up to 4 files), **listed ticker** (Yahoo Finance), **private CSV/Excel** (with a template download). Then: reporting-scale selector, KPI cards with sparklines and a full-history side panel, an auto-saving qualitative-notes box, a raw-data preview, the **credibility score** with its individual checks, per-agent readiness, and a **missing-data grid** with FMP / Alpha Vantage auto-fill for tickers. |
| `/analysis` | Runs the pipeline in the background with live per-stage progress, then shows the report in tabs (below). |
| `/workflow` | The agent pipeline as an interactive graph. It lights up live during a run and shows each step's guardrail. |
| `/basel` | Basel III alignment (static content). |
| `/history` | A table of completed analyses. |
| `/security` | Set up / disable 2FA (QR code), see active sessions and sign out the others, recent account activity. |
| `/admin/security` | Admin-only dashboard: 24-hour login, lockout, OTP and prompt-injection counts, top targeted accounts and IPs, and recent events. |

### The Analysis report (tabs)

The open tab is kept in the URL (`/analysis?tab=debt`), so refresh and back/forward work.

- **Overview** — credit grade, composite score, default-probability band, minimum DSCR, the weakest factor, a score-by-area chart, a sortable factor table, and data and risk alerts.
- **Trends** — revenue history plus a 3-year forecast with base / optimistic / pessimistic scenarios, and the operating-margin trend.
- **Metrics** — one category at a time (Risk signals, Revenue & SaaS, Profitability, Liquidity, Working capital, Solvency) as status-coloured tiles. Selecting a tile opens its meaning, the reason for its signal, and its formula.
- **Peers** — company vs peer median chart and a peer table, using live data only.
- **Debt service** — loan-terms form, then the DSCR by year (with the 1.0× danger line), amortisation schedule, stress tests and methodology. The minimum DSCR feeds back into the grade.
- **Assessment** — strengths, risks, narrative and findings from management commentary.
- **AI assistant** — plain-English explanation and a Q&A chat, both grounded in the computed facts only.
- **Memo** — a printable credit memo (open to print, or download).
- **Audit** — the agent workflow log and the raw computed data as JSON.

### Look and feel

Dark "glass" design with a **blue** accent, built on design tokens in `web/src/index.css`. Responsive down to phone
width. The accessibility basics are covered: labelled fields, keyboard-navigable tabs, focus handling in dialogs,
and status conveyed by text as well as colour.

## Backend (`api/`)

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register · login · login/mfa · logout`, `GET /api/auth/me`, `GET /api/geo/states · cities` |
| Password reset | `POST /api/password-reset/send-otp · verify-otp · reset` |
| Ingestion | `POST /api/ingest/pdf · ticker · csv`, `GET /api/ingest/csv-template` |
| Workspace | `GET/DELETE /api/workspace`, `PUT …/scale · qualitative`, `GET …/credibility`, `POST …/supplement/autofetch · apply` |
| Analysis | `POST /api/analysis`, `GET …/current · {id} · {id}/raw`, `POST {id}/dscr`, `POST {id}/assistant/explain · ask`, `GET {id}/memo` |
| History / Security | `GET /api/history`, `GET /api/security`, `POST …/mfa/begin · confirm · disable`, `POST …/sessions/revoke-others`, `GET /api/admin/security` |

Notable design points:

- **Background jobs.** The pipeline can run for a minute or more, so `POST /api/analysis` returns immediately and the
  browser polls for progress. One run per user is enforced atomically (a per-user lock with a heartbeat), and runs
  orphaned by a crash are detected and marked failed instead of hanging.
- **Sessions.** The JWT lives in an `httpOnly`, `SameSite=Strict` cookie with a CSRF header on every write. Sessions
  are checked against the database on every request (so logout and revocation take effect immediately) and expire
  after 15 minutes of inactivity.
- **No secrets leave the server.** The pipeline carries LLM keys and internal URLs in its state; these are stripped
  before anything is stored, and internal addresses are redacted from log text shown to users.
- **Uploads.** Size is capped before any body is parsed, file type is checked by content (not extension), and
  provider errors show a reference id instead of internals.
- **Per-user isolation.** Every query is filtered by the authenticated user's id; another user's analysis returns
  404, never 403.
- **File history now works.** In the old app the history table was always empty (the save function was never
  called). A row is now written when each analysis completes.

### Changes to existing code

All small and backward-compatible; the Streamlit app keeps working.

- `finveritas/analysis/workflow.py` — optional `on_step` callback and `PIPELINE_STAGES`, for live progress.
- `finveritas/auth/controller.py` — MFA-disable is now rate-limited; `reset_password` can make the write conditional
  so a reset token can't be redeemed twice at once.
- `finveritas/security/audit.py` — client IP can come from the API request.
- `finveritas/security/sessions.py` — `claims()` (token check without a DB hit) and `last_seen` on new sessions.
- `finveritas/auth/db.py` — `workspaces`, `analyses`, `analysis_locks` collections.

## Run it

```bash
# one-time
pip install -r requirements.txt
cd web && npm install && cd ..

# development — two terminals
uvicorn api.main:app --reload --port 8000      # API  (needs .env: JWT_SECRET, MONGO_URI)
cd web && npm run dev                           # UI → http://localhost:5173 (proxies /api to :8000)

# production-style — one server
cd web && npm run build && cd ..
uvicorn api.main:app --port 8000                # serves the API and the built UI
```

Useful environment variables (see `.env.example`): `JWT_SECRET`, `MONGO_URI`, `LLM_BASE_URL` / `LLM_MODEL` /
`LLM_API_KEY`, `FMP_API_KEY`, `ALPHA_VANTAGE_API_KEY` (optional, enables the second auto-fill provider),
`COOKIE_SECURE` (set `false` only for plain-http local testing), and **`TRUST_PROXY_HOPS`** — the number of reverse
proxies in front of the app (`1` on Render; `0` means client IPs in the audit log come straight from the connection).

Frontend checks: `npm run typecheck`, `npm test`, `npm run build`.

## Frontend stack

React 18 · TypeScript · Vite · Tailwind CSS 4 · TanStack Query · React Router · react-hook-form + zod · Recharts ·
React Flow. Fonts are self-hosted. `npm audit` reports no known vulnerabilities.

## Tests

- **Python:** the existing domain and security suites are unchanged. New API tests are in `tests/api/` (auth,
  ingestion, analysis). The analysis tests were written last and have **not yet been run to completion** — run
  `pytest tests` before merging.
- **Frontend:** unit tests for the money formatter and password rules (`web/src/lib/*.test.ts`).
- **Browser checks:** the main flows were exercised by hand in Chrome (register → load data → run → every tab →
  2FA setup), but there is no automated end-to-end suite yet.

## What's left

1. **Run the full test suite**, then add the missing tests (the review items below, an end-to-end browser test).
2. **Cutover:** multi-stage Dockerfile (Node build, then Python), point the container health check at
   `/api/health`, add a web job to `.github/workflows/ci-cd.yml`, update the Ansible vars.
3. **Remove Streamlit:** `app.py`, the `*/page.py` modules, `shared/components.py`, `styles.css`, `.streamlit/`, and the
   `streamlit` / `streamlit-agraph` dependencies — and port `tests/security/test_app_smoke.py`.
4. Optional: a light theme (the colours are already tokens), and moving long-running jobs out of process if the app
   is ever run on more than one instance.

## Code-review fixes included

A review of this branch found ten issues, all addressed: unthrottled MFA-disable guessing, forgeable client IP via
`X-Forwarded-For`, stale credibility after a scale change, credibility computed on unscaled data, double-started
analyses, a reset-token race, no request-size limit before upload parsing, wrong "latest period" ordering
(FY vs quarters), a doubled session lookup per request, and startup recovery that could kill another worker's live run.
