# FinVeritas — Shock Lab (scenario stress testing for SaaS borrowers)

> **Status: built (V3).** Sidebar → **Shock Lab**. A user picks an economic shock
> ("Eurozone recession", "Western banking stress", or their own words), watches it spread
> across industries and countries to the borrower's customers, lets the agents react
> quarter by quarter, and sees the stressed DSCR, credit grade and PD band.
>
> **FinVeritas works with SaaS companies only.** Shock Lab warns if the borrower was not
> classified as SaaS.

---

## 0. Where the idea comes from

The idea comes from **MiroFish** (github.com/666ghj/MiroFish), a swarm-intelligence engine: build a
digital world from seed information, populate it with agents that have personas and
memory, let them act round by round, inject events from a "God's-eye view", then read a
report and interview the agents. Shock Lab reuses those *ideas* (no MiroFish code) and
adapts them to credit underwriting:

| MiroFish | Shock Lab |
|---|---|
| Seed documents → knowledge graph | The analysed borrower record + its customer mix (region.sector) |
| Agents with personas & memory | Customer segments, Management (CFO), a Competitor — each with a persona and a memory of past quarters |
| Social-media actions (post, like, repost) | Credit-relevant actions from a fixed menu (renew, cut seats, churn; hiring freeze, cost cuts; price war) |
| Rounds = simulated hours | Rounds = quarters (4 = one stressed year) |
| God's-eye variable injection | Inject a second shock at quarter 2–4 |
| ReportAgent | AI-written stress-test note, grounded in computed facts |
| Interview any agent | Interview any agent about its decisions |
| Opinion prediction (no numbers) | **Numbers:** stressed revenue, EBITDA, DSCR, grade, PD band |

**The one rule still holds:** Python computes every number; AI only narrates.

---

## 1. How it works

```
Shock (preset, or text → LLM → ShockSpec, clamped and shown to the analyst)
   │
   ▼
propagate(): stress spreads through 15 region.sector nodes   ← numpy, x = (I − d·W)⁻¹ s
   │
   ▼
Each quarter, every agent sees its stress and picks ONE action from its menu
   │   rules (official, deterministic)  or  LLM (exploratory, falls back to rules)
   ▼
Python applies each action's fixed effect to ARR and costs
   │
   ▼
stress_record(): a stressed COPY of NormalizedCompanyRecord (latest year shifted)
   │
   ├─► compute_dscr_schedule(stressed, terms + rate shock)   ← existing engine, unchanged
   ├─► compute_scorecard(stressed, min_dscr)                 ← existing engine, unchanged
   ▼
Base vs Shock (rules) vs Shock (AI): revenue, EBITDA, min DSCR, grade, PD band
```

### 1.1 The economy (contagion)

- Nodes: `US / EU / IN` × `tech / finance / manufacturing / retail / energy`.
- Links: the same sector across regions (e.g. US → EU 0.30), supply chains within a
  region (energy → manufacturing 0.40, finance → tech 0.30, …), plus direct links
  `US.finance → IN.tech` and `EU.finance → IN.tech` (Indian IT sells to Western banks).
- Damping 0.5; the largest knock-on multiplier is about 1.15×.
- Weights are hand-set; the upgrade path is OECD ICIO input-output shares.

### 1.2 Agents and actions (effects in the quarter taken)

| Agent | Actions |
|---|---|
| Customer segment | EXPAND +3% ARR · RENEW · ASK_DISCOUNT −2% · CUT_SEATS −5% · PARTIAL_CHURN −12% |
| Management (CFO) | HOLD_COURSE · HIRING_FREEZE opex −3% · COST_CUTS opex −7%, stress +2 next · RAISE_PRICES all ARR +2%, stress +3 next · RETENTION_DISCOUNTS all ARR −2%, stress −4 next |
| Competitor | HOLD_PRICES · PRICE_WAR stress +5 next |

Rule policy (official), by stress = % of demand lost:
customers `< −5 EXPAND, < 2 RENEW, < 8 ASK_DISCOUNT, < 15 CUT_SEATS, else PARTIAL_CHURN`;
management `< 5 HOLD, < 12 HIRING_FREEZE, else COST_CUTS`; competitor `≥ 10 PRICE_WAR`.

### 1.3 From ARR to the credit numbers

- Baseline quarterly growth comes from the borrower's latest YoY revenue growth (clamped −10%…+40%/yr).
- Revenue change = stressed vs no-shock revenue over the 4 quarters.
- EBITDA change = revenue change × gross margin − extra cloud cost + management savings.
- Net income / OCF / FCF change = EBITDA change × (1 − tax rate).
- Applied to the **latest reported year**, matching the DSCR engine's constant-numerator convention.
- Rate shocks raise the loan's interest rate in the DSCR schedule.

### 1.4 Presets

Eurozone recession · US tech budget freeze · Western banking stress · Energy crisis ·
Global rate shock (+200 bps) · Cloud cost spike (cost of revenue +25%) · AI-native competitor price war.

---

## 2. Files

| File | Role |
|---|---|
| `finveritas/analysis/metrics/shock.py` | Deterministic engine: graph, `propagate`, `ShockSpec`, presets, agents, `rule_policy`, `simulate`, `stress_record`, `credit_view` |
| `finveritas/analysis/shock_agents.py` | AI layer: `interpret_scenario`, `make_llm_policy`, `interview`, `write_report` |
| `finveritas/analysis/shock_page.py` | The Shock Lab page (6 steps) |
| `tests/test_shock.py` | Engine tests (no LLM needed) |
| `app.py` | Sidebar entry + route |

Loan terms come from **Financial Analysis → Debt Serviceability** (`v3_dscr_terms`);
without them the grade is shown without DSCR.

---

## 3. Guardrails

- AI-drafted shocks pass through `ShockSpec`, which clamps every value and drops unknown
  nodes, and the spec is shown before running.
- Every AI decision is validated against the agent's menu; anything else falls back to the
  rules, and the timeline shows who decided ("AI" or "rules").
- After 3 consecutive LLM failures the AI run stops calling the LLM, so a down endpoint
  costs seconds, not minutes.
- The official result always uses the rules. The AI run is labelled exploratory.

---

## 4. Next steps

- [ ] Shocks that vary by loan year: `_min_dscr_for` takes one cash figure for all years; make it accept one per year
- [ ] Expected loss: EL = PD × LGD × EAD, as a range from the PD band
- [ ] Add the stress outcome to the Credit Memo and the AI Assistant's context
- [ ] Portfolio stress across saved borrowers (needs "Persist analyses to MongoDB")
- [ ] Calibrate link weights from OECD ICIO; backtest a COVID preset on FY2019 → FY2021 actuals

*Updated: 2026-10-04.*
