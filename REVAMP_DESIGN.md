# FinVeritas — End-to-End Revamp Blueprint (domain-expert walkthrough)

> I used the system as a credit analyst would, start to finish, and wrote down every
> place the content, numbers, messaging, or flow gets in the way — plus the target
> design and where AI genuinely helps. This is the reference the V3 build follows.
> Nothing here is locked; it's the plan, and it will be ticked off in verified increments.

---

## 0. What the product is (the North Star)

A **credit underwriting assistant**: an analyst gives it a borrower (+ optionally a
proposed loan) and gets a clear, defensible read on **can they repay, how risky, on what
terms** — every number reproducible, every judgment explained.

**The one rule that never bends:** Python computes every number; AI only explains,
summarizes, or answers questions *about* the numbers. AI never produces a figure, ratio,
grade, or default probability.

---

## 1. Cross-cutting standards (apply on every screen)

These are the things that were inconsistent and made the app hard to read:

- **Money:** always a currency symbol + human scale — `$416.16B`, `₹1.2Cr/…B`, never
  `416,161.00M`. (Done via `format_money`.)
- **Periods:** `FY 2025`, `Q3 2024` — never `2025-FY`. Always say whether a figure is the
  latest actual vs a projection. (Done via `_fmt_period`.)
- **Currency comparability:** when comparing companies, convert to one base currency and
  say so. (Engine done in `currency.py`; wire into peer/benchmark views.)
- **Every metric gets a plain-language "what this means"** on hover/expand — not just the
  formula. A number without meaning is noise.
- **Message states must always be handled:** empty ("no data yet — do X"), loading
  ("fetching… / computing…"), error (what failed + how to fix), and success. No blank
  panels, no raw tracebacks in the user's face.
- **Raw JSON/logs live behind a Developer toggle**, never in the main flow. (Done.)
- **Consistent status colors:** green = healthy/pass, amber = watch/warn, red =
  breach/fail, grey = no data. Used identically everywhere.

---

## 2. The target user journey

```
Login  →  New Analysis
            │
            ├─ 1. Choose borrower & source (ticker / PDF / CSV)   → auto-fetch
            ├─ 2. Data review: what we got, what's missing, credibility  → proceed/supplement
            ├─ 3. (optional) Proposed loan terms                  → for DSCR
            └─ 4. Results: one scrollable "Credit Report"
                   ├─ Verdict banner  (grade · risk · one-line concern)
                   ├─ Trends & forecast
                   ├─ Debt serviceability (DSCR schedule + stress)
                   ├─ Metrics dashboard (by category, each explained)
                   ├─ Peer benchmarking (currency-normalized, percentiles)
                   ├─ Qualitative context (soft, clearly separated)
                   ├─ AI narrative + "Ask about this company"
                   └─ Download Credit Memo (PDF)
```

The current app scatters this across four disconnected pages with a clunky "go back and
re-run" loop for DSCR. Target: **one coherent report the analyst reads top to bottom.**

---

## 3. Page-by-page: issues → target

### Login / Landing
- **Issue:** described the old "5 AI agents / Sentiment" (fixed). 
- **Target:** a tight value line + "what you'll get" (a credit grade, DSCR, peer view, a
  downloadable memo). Set expectations honestly.

### Upload / New Analysis
- **Issues:** raw numbers (fixed); confusing "Credit Risk Agent will use this text"
  (fixed); phantom Sentiment badge (fixed); no clear "what happens next."
- **Target:** a 3-step wizard feel — pick source → **data review card** (fields captured,
  what's missing, credibility score, currency detected) → run. Show a friendly summary:
  "Loaded Apple Inc. — 24 of 28 fields, FY2021–FY2025, USD. Missing: quarterly data."

### Results (today: "Financial Analysis")
- **Issues:** a dense wall; DSCR needs a re-run round-trip; metrics without meaning; raw
  JSON in the middle (fixed); no top-level verdict.
- **Target:** lead with a **Verdict banner** ("BBB · Moderate risk · Watch: high
  leverage"), then the sections in the journey order above. DSCR inline (no re-run).
  Each metric card carries a one-line meaning + status color.

### Agent Workflow / Basel pages
- **Target:** fold the useful transparency (which step did what, guardrails) into a
  collapsible "How this was computed" panel inside the report, instead of separate pages.
  Keep Basel context as a short, honest footnote, not a page pretending at compliance.

---

## 4. Where AI is added, and how (the interesting part)

AI is used **only** in these roles, always downstream of the deterministic numbers:

1. **Narrative synthesis (exists, harden it):** turn the computed facts into a readable
   assessment. Fix: force structured/JSON output + validation so it stops coming back
   blank; allow a stronger model endpoint.
2. **On-demand "explain this" (new):** a button on any metric/section → AI explains *this
   company's* number in plain English, citing the computed value. ("Your DSCR of 1.2x
   means…"). Never recalculates.
3. **"Ask about this company" chat (new):** a scoped Q&A that can *only* reference the
   fact ledger + report. Guardrailed so it answers from computed data, says "not in the
   data" otherwise, and never invents figures.
4. **Qualitative extraction (exists, wire data in):** pull credit-relevant points from
   pasted commentary. Keep strictly separate from the score.
5. **Company classification (exists, de-SaaS it):** broaden beyond "is this SaaS" to
   general industry, which then drives industry-aware thresholds.
6. **Anomaly explanation (new, optional):** deterministic engine flags an odd jump; AI
   explains what *kind* of thing could cause it (never asserts the cause as fact).

**Guardrail pattern for all AI:** system prompt says "these numbers are authoritative,
do not change them, do not add new figures"; output is validated; on failure we degrade
gracefully to the deterministic data with a clear "narrative unavailable" note.

---

## 5. Backend upgrades that unlock the above

- **De-SaaS the core:** run the SaaS engine only for software companies; replace the
  SaaS-worded thresholds with the industry-aware ones; broaden the classification prompt.
- **One source of truth per number:** retire the duplicate V1 calculators.
- **Persist analyses to MongoDB:** history + re-open + compare the same borrower over time.
- **Peer view:** currency-normalize, add percentile positioning + a radar chart.
- **Working-capital cycle** (DSO/DIO/DPO), **cash-flow-based liquidity**, and an
  **anomaly/alerts** engine — all deterministic, all feeding the scorecard and memo.

---

## 6. Build order (what gets done, next first)

- [x] Currency/period/units readable everywhere (started — Upload cards done)
- [ ] Unify results into one report with a **Verdict banner** at the top
- [ ] Inline DSCR (kill the re-run round-trip)
- [ ] "What this means" on every metric + consistent status colors
- [ ] De-SaaS the engine (industry-correct metrics for all companies)
- [ ] AI: harden narrative (structured output) + "Explain this" buttons
- [ ] AI: scoped "Ask about this company" chat
- [ ] Peer view: currency-normalized + percentiles + radar
- [ ] Persist analyses (history / compare over time)
- [ ] Working-capital + anomaly/alerts engines
- [ ] Retire duplicate V1 calculators; final polish pass

*Last updated: 2026-09-24. Built on branch `V3-revamp`.*
