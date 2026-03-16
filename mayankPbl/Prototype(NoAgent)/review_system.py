"""Entity-first, explainable financial background review prototype.

This script:
1. Loads structured financial data from `as.json` (the ONLY data source).
2. Parses quarterly time-series into pandas DataFrames.
3. Runs modular, agent-based analyses:
   - Revenue Stability Agent
   - Cash Flow Agent
   - Liability / Leverage Agent
   - Cross-Reference Agent (consumes only agent outputs)
4. Applies an explicit, rule-based review layer that can flag for manual review
   but never overrides or hides agent analysis.
5. Prints structured, human-readable output to the console.

Design goals:
- Deterministic, auditable, and conservative in interpretation.
- No ML, no forecasting/prediction, no external APIs.
- All numeric values are read from `as.json` at runtime; nothing is hardcoded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


# ----------------------------
# Data loading and validation
# ----------------------------


def load_data(json_path: Path) -> Dict[str, Any]:
    """Load and minimally validate the as.json file.

    Notes:
    - This function does *not* attempt to correct or impute data.
    - It only checks for the core structural elements we expect.
    """

    if not json_path.exists():
        raise FileNotFoundError(f"Data file not found: {json_path}")

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Basic structure validation – conservative and explicit
    required_top_keys = {"entity", "time_series", "metadata"}
    missing = required_top_keys - set(data.keys())
    if missing:
        raise ValueError(f"Missing required top-level keys in JSON: {sorted(missing)}")

    ts = data.get("time_series", {})
    for series_name in ("revenue", "cash_flow", "liabilities"):
        if series_name not in ts:
            raise ValueError(f"Missing time_series entry for '{series_name}' in JSON")

    return data


# ----------------------------
# Helper utilities
# ----------------------------


def _ensure_ordered_quarterly(df: pd.DataFrame, period_col: str = "period") -> pd.DataFrame:
    """Return DataFrame ordered by the given period column.

    Assumes period labels like "YYYY-QN". For robustness, we split on '-' and 'Q'.
    We only use ordering logic; we do not transform or rescale values.
    """

    if period_col not in df.columns:
        raise ValueError(f"Expected column '{period_col}' in DataFrame")

    def _period_key(p: str) -> tuple[int, int]:
        try:
            year_str, q_str = p.split("-")
            q_num = int(q_str.replace("Q", ""))
            return int(year_str), q_num
        except Exception:
            # Fallback: leave as-is if format is unexpected
            return 0, 0

    df = df.copy()
    df["_year"], df["_quarter"] = zip(*df[period_col].map(_period_key))
    df = df.sort_values(by=["_year", "_quarter"]).reset_index(drop=True)
    df = df.drop(columns=["_year", "_quarter"])
    return df


@dataclass
class MetricResult:
    """Container for interpretable numeric metrics for a single series."""

    trend_direction: str
    trend_slope_per_period: Optional[float]
    volatility_ratio: Optional[float]
    volatility_classification: str
    persistence_of_improvement: Optional[float]
    notes: List[str] = field(default_factory=list)


@dataclass
class AgentOutput:
    """Standard output format for all analytical agents."""

    agent_name: str
    series_name: str
    metrics: MetricResult
    narrative: str


def compute_basic_time_series_metrics(values: pd.Series) -> MetricResult:
    """Compute simple interpretable metrics on a 1D numeric time series.

    Metrics:
    - trend_direction: based on sign of net change from first to last point.
    - trend_slope_per_period: (last - first) / (n_periods - 1), if possible.
    - volatility_ratio: std / mean if mean != 0 and length > 1, else None.
    - volatility_classification: low/medium/high relative only to this series.
      Thresholds are explicit below and are not statistically optimized.
    - persistence_of_improvement: fraction of periods where value increased
      vs the immediately previous period.

    Assumptions are documented in comments and reflected in the narrative.
    """

    notes: List[str] = []

    if values.empty:
        return MetricResult(
            trend_direction="insufficient data",
            trend_slope_per_period=None,
            volatility_ratio=None,
            volatility_classification="unknown",
            persistence_of_improvement=None,
            notes=["No data points available in series"],
        )

    # Trend direction and slope
    first = values.iloc[0]
    last = values.iloc[-1]

    if len(values) == 1:
        net_change = 0.0
        slope = None
        trend_direction = "flat (single observation)"
        notes.append("Only one observation; treating trend as flat and slope as undefined.")
    else:
        net_change = float(last) - float(first)
        slope = net_change / (len(values) - 1)
        if net_change > 0:
            trend_direction = "increasing"
        elif net_change < 0:
            trend_direction = "decreasing"
        else:
            trend_direction = "flat"

    # Volatility relative to the mean (no rescaling of underlying values)
    if len(values) > 1 and values.mean() != 0:
        vol_ratio = float(values.std(ddof=0) / values.mean())

        # Explicit, simple thresholds for interpretation.
        # These are *relative only to this series* and intentionally simple:
        # - low:   volatility_ratio < 0.05  (std < 5% of mean)
        # - medium:0.05 <= ratio <= 0.15
        # - high:  ratio > 0.15
        if vol_ratio < 0.05:
            vol_class = "low"
        elif vol_ratio <= 0.15:
            vol_class = "medium"
        else:
            vol_class = "high"

        notes.append(
            "Volatility interpreted as std/mean with thresholds: "
            "<0.05 low, 0.05-0.15 medium, >0.15 high."
        )
    else:
        vol_ratio = None
        vol_class = "unknown"
        notes.append("Volatility not computed (insufficient observations or zero mean).")

    # Persistence of improvement: percentage of positive period-over-period changes.
    if len(values) > 1:
        deltas = values.diff().dropna()
        improving_periods = (deltas > 0).sum()
        persistence = float(improving_periods) / float(len(deltas))
    else:
        persistence = None
        notes.append("Persistence not computed (only one observation).")

    return MetricResult(
        trend_direction=trend_direction,
        trend_slope_per_period=slope,
        volatility_ratio=vol_ratio,
        volatility_classification=vol_class,
        persistence_of_improvement=persistence,
        notes=notes,
    )


# ----------------------------
# Analytical Agents
# ----------------------------


class BaseAgent:
    """Base class for all analytical agents.

    Subclasses must implement `analyze` and should not perform any I/O.
    They operate strictly on data passed in as arguments.
    """

    name: str = "base-agent"

    def analyze(self, df: pd.DataFrame) -> AgentOutput:  # pragma: no cover - interface
        raise NotImplementedError


class RevenueStabilityAgent(BaseAgent):
    name = "Revenue Stability Agent"

    def analyze(self, df: pd.DataFrame) -> AgentOutput:
        # df is expected to have columns: period, value
        df_ordered = _ensure_ordered_quarterly(df)
        metrics = compute_basic_time_series_metrics(df_ordered["value"])

        narrative_lines = [
            f"Analyzing revenue over {len(df_ordered)} quarterly observations.",
            f"Trend direction: {metrics.trend_direction}.",
        ]
        if metrics.trend_slope_per_period is not None:
            narrative_lines.append(
                f"Approximate net change per quarter: {metrics.trend_slope_per_period:.2f} (in reported units)."
            )
        if metrics.volatility_ratio is not None:
            narrative_lines.append(
                "Volatility (std/mean) is "
                f"{metrics.volatility_ratio:.4f}, classified as {metrics.volatility_classification}."
            )
        else:
            narrative_lines.append(
                f"Volatility classification: {metrics.volatility_classification} (not enough information)."
            )
        if metrics.persistence_of_improvement is not None:
            narrative_lines.append(
                "Revenue improved in "
                f"{metrics.persistence_of_improvement * 100:.1f}% of observed intervals."
            )
        narrative_lines.extend(metrics.notes)

        return AgentOutput(
            agent_name=self.name,
            series_name="revenue",
            metrics=metrics,
            narrative=" ".join(narrative_lines),
        )


class CashFlowAgent(BaseAgent):
    name = "Cash Flow Agent"

    def analyze(self, df: pd.DataFrame) -> AgentOutput:
        df_ordered = _ensure_ordered_quarterly(df)
        metrics = compute_basic_time_series_metrics(df_ordered["value"])

        narrative_lines = [
            f"Analyzing operating cash flow over {len(df_ordered)} quarterly observations.",
            f"Trend direction: {metrics.trend_direction}.",
        ]
        if metrics.trend_slope_per_period is not None:
            narrative_lines.append(
                f"Approximate net change per quarter: {metrics.trend_slope_per_period:.2f} (in reported units)."
            )
        if metrics.volatility_ratio is not None:
            narrative_lines.append(
                "Volatility (std/mean) is "
                f"{metrics.volatility_ratio:.4f}, classified as {metrics.volatility_classification}."
            )
        else:
            narrative_lines.append(
                f"Volatility classification: {metrics.volatility_classification} (not enough information)."
            )
        if metrics.persistence_of_improvement is not None:
            narrative_lines.append(
                "Cash flow improved in "
                f"{metrics.persistence_of_improvement * 100:.1f}% of observed intervals."
            )
        narrative_lines.extend(metrics.notes)

        return AgentOutput(
            agent_name=self.name,
            series_name="cash_flow",
            metrics=metrics,
            narrative=" ".join(narrative_lines),
        )


class LiabilityLeverageAgent(BaseAgent):
    name = "Liability / Leverage Agent"

    def analyze(self, df: pd.DataFrame) -> AgentOutput:
        # df is expected to have columns: period, debt, equity
        df_ordered = _ensure_ordered_quarterly(df)

        # Compute simple leverage ratio: debt/equity for each period, if equity != 0.
        # No rescaling or normalization of underlying values.
        leverage_series = []
        notes: List[str] = []
        for _, row in df_ordered.iterrows():
            equity = row.get("equity")
            debt = row.get("debt")
            if equity in (0, None):
                notes.append(
                    f"Equity is zero or missing in period {row['period']}; leverage ratio not computed for that period."
                )
                leverage_series.append(None)
            else:
                leverage_series.append(float(debt) / float(equity))

        leverage = pd.Series(leverage_series)

        # For metrics, we only use periods where leverage ratio is defined.
        valid_leverage = leverage.dropna()
        metrics = compute_basic_time_series_metrics(valid_leverage) if not valid_leverage.empty else MetricResult(
            trend_direction="insufficient data",
            trend_slope_per_period=None,
            volatility_ratio=None,
            volatility_classification="unknown",
            persistence_of_improvement=None,
            notes=["No valid leverage observations (e.g., equity missing or zero)."],
        )
        metrics.notes.extend(notes)

        narrative_lines = [
            f"Analyzing leverage (debt/equity) over {len(valid_leverage)} valid quarterly observations.",
            f"Trend direction in leverage: {metrics.trend_direction}.",
        ]
        if metrics.trend_slope_per_period is not None:
            narrative_lines.append(
                "Approximate net change in leverage ratio per quarter: "
                f"{metrics.trend_slope_per_period:.4f}."
            )
        if metrics.volatility_ratio is not None:
            narrative_lines.append(
                "Leverage volatility (std/mean) is "
                f"{metrics.volatility_ratio:.4f}, classified as {metrics.volatility_classification}."
            )
        else:
            narrative_lines.append(
                "Leverage volatility classification: "
                f"{metrics.volatility_classification} (not enough information)."
            )
        if metrics.persistence_of_improvement is not None:
            narrative_lines.append(
                "Leverage decreased (improved) in "
                f"{metrics.persistence_of_improvement * 100:.1f}% of intervals, "
                "where 'improvement' is defined as a lower debt/equity ratio."
            )
        narrative_lines.extend(metrics.notes)

        return AgentOutput(
            agent_name=self.name,
            series_name="liabilities/leverage",
            metrics=metrics,
            narrative=" ".join(narrative_lines),
        )


# ----------------------------
# Cross-Reference Agent
# ----------------------------


@dataclass
class CrossReferenceOutput:
    """Output of the cross-reference agent.

    Contains a consolidated narrative plus a structured view of
    reinforcing vs conflicting signals.
    """

    reinforcing_signals: List[str]
    conflicting_signals: List[str]
    narrative: str


class CrossReferenceAgent:
    """Consumes only AgentOutput objects and cross-references their signals.

    This agent does *not* access raw numeric data. It operates purely on the
    interpretable metrics and narratives produced by the upstream agents.
    """

    name = "Cross-Reference Agent"

    def analyze(self, agent_outputs: List[AgentOutput]) -> CrossReferenceOutput:
        reinforcing: List[str] = []
        conflicting: List[str] = []

        # Very conservative, rule-based comparison logic based solely on
        # trend_direction and volatility_classification.
        rev = self._find(agent_outputs, "revenue")
        cf = self._find(agent_outputs, "cash_flow")
        lev = self._find(agent_outputs, "liabilities/leverage")

        # Helper to describe a direction in a human-readable way
        def describe(agent_label: str, metric: MetricResult) -> str:
            return (
                f"{agent_label}: trend={metric.trend_direction}, "
                f"volatility={metric.volatility_classification}."
            )

        if rev and cf:
            if rev.metrics.trend_direction == cf.metrics.trend_direction:
                reinforcing.append(
                    "Revenue and cash flow show a similar trend direction, "
                    "which reinforces the observed pattern in core operations."
                )
            else:
                conflicting.append(
                    "Revenue and cash flow trends differ, which may warrant "
                    "closer review of the cash conversion profile."
                )

        if lev and rev:
            # If revenue is increasing and leverage is decreasing, that is reinforcing.
            if (
                rev.metrics.trend_direction == "increasing"
                and lev.metrics.trend_direction == "decreasing"
            ):
                reinforcing.append(
                    "Increasing revenue combined with decreasing leverage "
                    "suggests improving balance sheet position relative to scale."
                )
            # If revenue is flat/decreasing while leverage is increasing, that is a
            # potentially conflicting or conservative signal.
            if rev.metrics.trend_direction in {"flat", "decreasing"} and lev.metrics.trend_direction == "increasing":
                conflicting.append(
                    "Leverage appears to be rising while revenue is not clearly "
                    "increasing, which may warrant additional scrutiny."
                )

        # Narrative synthesis – descriptive only, no verdict.
        narrative_parts: List[str] = [
            "Cross-Reference Agent reviewed the outputs of the individual agents.",
        ]

        if rev:
            narrative_parts.append("Revenue summary: " + describe("Revenue", rev.metrics))
        if cf:
            narrative_parts.append("Cash flow summary: " + describe("Cash flow", cf.metrics))
        if lev:
            narrative_parts.append("Leverage summary: " + describe("Leverage", lev.metrics))

        if reinforcing:
            narrative_parts.append(
                "Identified reinforcing signals: " + " ".join(reinforcing)
            )
        if conflicting:
            narrative_parts.append(
                "Identified potentially conflicting signals: " + " ".join(conflicting)
            )

        if not reinforcing and not conflicting:
            narrative_parts.append(
                "No clear reinforcing or conflicting patterns were detected "
                "based on the simple comparison rules applied."
            )

        return CrossReferenceOutput(
            reinforcing_signals=reinforcing,
            conflicting_signals=conflicting,
            narrative=" ".join(narrative_parts),
        )

    @staticmethod
    def _find(agent_outputs: List[AgentOutput], series_name: str) -> Optional[AgentOutput]:
        for out in agent_outputs:
            if out.series_name == series_name:
                return out
        return None


# ----------------------------
# Rule-Based Review Layer
# ----------------------------


@dataclass
class RuleResult:
    rule_name: str
    triggered: bool
    description: str
    rationale: str


class RuleEngine:
    """Explicit, readable guardrail rules.

    Rules:
    - Do not overwrite or hide underlying agent analysis.
    - Only indicate whether additional manual review may be warranted.
    - Use simple, transparent conditions on already-computed metrics.
    """

    def evaluate(self, agent_outputs: List[AgentOutput], xref: CrossReferenceOutput) -> List[RuleResult]:
        results: List[RuleResult] = []

        rev = CrossReferenceAgent._find(agent_outputs, "revenue")
        cf = CrossReferenceAgent._find(agent_outputs, "cash_flow")
        lev = CrossReferenceAgent._find(agent_outputs, "liabilities/leverage")

        # Rule 1: Flag if revenue volatility is high.
        if rev is not None:
            trig = rev.metrics.volatility_classification == "high"
            results.append(
                RuleResult(
                    rule_name="High revenue volatility guardrail",
                    triggered=trig,
                    description=(
                        "Flags for manual review if revenue volatility, measured as std/mean "
                        "within the observed period, is classified as 'high' under the explicit "
                        "thresholds documented in the metrics computation."
                    ),
                    rationale=(
                        f"Revenue volatility classification is "
                        f"'{rev.metrics.volatility_classification}'."
                    ),
                )
            )

        # Rule 2: Flag if cash flow trend is decreasing while revenue is increasing.
        if rev is not None and cf is not None:
            trig = (
                rev.metrics.trend_direction == "increasing"
                and cf.metrics.trend_direction == "decreasing"
            )
            results.append(
                RuleResult(
                    rule_name="Divergent revenue and cash flow trend guardrail",
                    triggered=trig,
                    description=(
                        "Flags for manual review if revenue shows an increasing trend while "
                        "cash flow shows a decreasing trend, indicating potential issues in "
                        "cash conversion or working capital dynamics."
                    ),
                    rationale=(
                        f"Revenue trend is '{rev.metrics.trend_direction}', "
                        f"cash flow trend is '{cf.metrics.trend_direction}'."
                    ),
                )
            )

        # Rule 3: Flag if leverage trend is increasing.
        if lev is not None:
            trig = lev.metrics.trend_direction == "increasing"
            results.append(
                RuleResult(
                    rule_name="Rising leverage guardrail",
                    triggered=trig,
                    description=(
                        "Flags for manual review if leverage (debt/equity) shows an increasing "
                        "trend across the observation window."
                    ),
                    rationale=(
                        f"Leverage trend direction is '{lev.metrics.trend_direction}'."
                    ),
                )
            )

        # Rule 4: Flag if Cross-Reference Agent found conflicting signals.
        trig_conflict = len(xref.conflicting_signals) > 0
        results.append(
            RuleResult(
                rule_name="Cross-agent conflict guardrail",
                triggered=trig_conflict,
                description=(
                    "Flags for manual review if the Cross-Reference Agent identifies "
                    "potentially conflicting signals between agents."
                ),
                rationale=(
                    "Number of conflicting signals identified by Cross-Reference Agent: "
                    f"{len(xref.conflicting_signals)}."
                ),
            )
        )

        return results


# ----------------------------
# Orchestration and Reporting
# ----------------------------


def run_review(json_filename: str = "as.json") -> None:
    """End-to-end orchestration of the review process.

    Steps:
    1. Load and validate data from the JSON file in the current directory.
    2. Parse time-series data into pandas DataFrames.
    3. Execute each analytical agent independently.
    4. Run cross-reference analysis.
    5. Apply the rule-based review layer.
    6. Print a structured, explainable report to the console.
    """

    json_path = Path(__file__).resolve().parent / json_filename
    data = load_data(json_path)

    entity = data["entity"]
    ts = data["time_series"]
    meta = data["metadata"]

    # Parse time-series into DataFrames without altering values.
    revenue_df = pd.DataFrame(ts["revenue"])
    cash_flow_df = pd.DataFrame(ts["cash_flow"])
    liabilities_df = pd.DataFrame(ts["liabilities"])

    # Instantiate agents
    revenue_agent = RevenueStabilityAgent()
    cash_agent = CashFlowAgent()
    lev_agent = LiabilityLeverageAgent()
    xref_agent = CrossReferenceAgent()
    rules_engine = RuleEngine()

    # Run analytical agents independently
    agent_outputs: List[AgentOutput] = []
    agent_outputs.append(revenue_agent.analyze(revenue_df))
    agent_outputs.append(cash_agent.analyze(cash_flow_df))
    agent_outputs.append(lev_agent.analyze(liabilities_df))

    # Cross-reference analysis (operates only on agent outputs)
    xref_output = xref_agent.analyze(agent_outputs)

    # Apply rule-based review layer
    rule_results = rules_engine.evaluate(agent_outputs, xref_output)

    # ------------------------
    # Structured console report
    # ------------------------

    unit = meta.get("unit_of_measurement", "(reported units)")

    print("=" * 80)
    print("ENTITY BACKGROUND REVIEW (Prototype)")
    print("=" * 80)
    print(f"Entity ID: {entity.get('entity_id')}")
    print(f"Type: {entity.get('type')} | Industry: {entity.get('industry')} | Currency: {entity.get('currency')}")
    print(
        f"Observation window: {meta.get('observation_window_months')} months, "
        f"reporting frequency: {meta.get('reporting_frequency')} | units: {unit}"
    )
    print()

    # Individual agent findings
    print("--- Individual Agent Findings ---")
    for out in agent_outputs:
        print()
        print(f"[{out.agent_name} – {out.series_name}]")
        m = out.metrics
        print("Trend direction:", m.trend_direction)
        if m.trend_slope_per_period is not None:
            print(
                f"Approximate slope per period: {m.trend_slope_per_period:.4f} {unit} per quarter (as reported)."
            )
        else:
            print("Approximate slope per period: not computed (insufficient data).")
        if m.volatility_ratio is not None:
            print(
                f"Volatility (std/mean): {m.volatility_ratio:.4f} "
                f"=> classification: {m.volatility_classification} (relative to this series only)."
            )
        else:
            print(
                "Volatility: not computed => classification: "
                f"{m.volatility_classification}."
            )
        if m.persistence_of_improvement is not None:
            print(
                f"Persistence of improvement: {m.persistence_of_improvement * 100:.1f}% "
                "of intervals showed improvement by the simple period-over-period rule."
            )
        else:
            print("Persistence of improvement: not computed (insufficient data).")

        print("Narrative:")
        print("  " + out.narrative)

    # Cross-reference findings
    print()
    print("--- Cross-Reference Analysis ---")
    print(xref_output.narrative)

    # Rule-based review
    print()
    print("--- Rule-Based Review (Guardrails Only) ---")
    for rr in rule_results:
        status = "TRIGGERED" if rr.triggered else "not triggered"
        print(f"Rule: {rr.rule_name} -> {status}")
        print(f"  Description: {rr.description}")
        print(f"  Rationale:   {rr.rationale}")

    # Consolidated explanation (no verdict)
    print()
    print("--- Consolidated Explanation (Descriptive Only) ---")
    print(
        "This prototype reviews the entity on an agent-by-agent basis, then "
        "cross-references their interpretable metrics. The rule engine adds "
        "transparent guardrails that may flag areas for manual review but does "
        "not approve, reject, or score the entity. All quantities and trends "
        "are derived directly from the quarterly data in 'as.json' without "
        "any rescaling, normalization, or prediction."
    )


if __name__ == "__main__":
    # Example execution when run as a script.
    run_review()
