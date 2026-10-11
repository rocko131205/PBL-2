import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";

/* ── Shapes returned by api/routers/analysis.py and api/report.py ──────── */

export type RunStatus = "queued" | "running" | "done" | "failed";
export interface Stage { key: string; label: string; status: "pending" | "running" | "done" }
export type Signal = "PASS" | "WARN" | "FAIL" | null;

export interface Verdict {
  grade: string; grade_label: string; composite: number; pd_band: string;
  min_dscr: number | null; watch: { name: string; note: string } | null;
}
export interface Factor {
  key: string; name: string; bucket: string; value: number | null; unit: string;
  score: number | null; weight: number; contribution: number | null; note: string; status: string;
}
export interface Scorecard {
  grade: string; grade_label: string; pd_band: string; composite_score: number;
  industry_profile: string; covered_weight: number; buckets: Record<string, number | null>;
  factors: Factor[]; notes: string[];
}
/** VALID is a computed figure; ESTIMATED used a disclosed assumption; the rest mean there is no number, and why. */
export type FactStatus = "VALID" | "ESTIMATED" | "INSUFFICIENT_DATA" | "NOT_APPLICABLE"
  | "REQUIRES_ADDITIONAL_DOCUMENT" | "REQUIRES_EXTERNAL_DATA";

export interface LedgerRow {
  metric: string; name: string; value: number | string | null; display: string; signal: Signal;
  signal_detail: string | null; formula: string | null; meaning: string; period: string | null;
  status?: FactStatus; note?: string | null;
}
export interface LedgerSection { category: string; title: string; rows: LedgerRow[] }
export interface TrendRow {
  period: string; history?: number; base?: number; optimistic?: number; pessimistic?: number;
  band?: [number, number]; forecast?: boolean;
}
export interface Trends {
  revenue: { rows: TrendRow[]; cagr_pct: number | null; optimistic_growth_pct: number | null;
    pessimistic_growth_pct: number | null; latest_display: string | null; assumptions: string[] };
  margin: { rows: { period: string; margin: number }[]; first: number; last: number; trend: string } | null;
}
export interface Peer {
  entity_id: string; ticker?: string | null; peer_tier: string; revenue_growth?: number | null;
  operating_margin?: number | null; gross_margin?: number | null; debt_to_equity?: number | null;
}
export interface RiskIndicator { name: string; category: string; status: "PASS" | "WARN" | "FAIL" | "SKIP"; detail: string }
export interface DscrRow {
  year: number; principal: number; interest: number; total_payment: number; dscr: number | null;
  principal_display: string; interest_display: string; total_payment_display: string;
}
export interface DscrView {
  numerator_basis: string; numerator_display: string; min_dscr: number | null; avg_dscr: number | null;
  min_dscr_year: number | null; risk_level: string; interest_coverage: number | null; debt_to_ebitda: number | null;
  schedule: DscrRow[]; dscr_by_year: (number | null)[]; tenure_years: number;
  stress_results: { scenario: string; description: string; min_dscr: number | null; delta_vs_base: number | null; breaches_1x: boolean }[];
  verdict: { tone: "good" | "watch" | "risk"; text: string } | null; method: string[]; notes: string[]; breaches: number;
}
export interface DscrTerms {
  principal: number; annual_rate_pct: number; tenure_years: number; structure: string;
  moratorium_years: number; existing_annual_debt_service: number; basis: string;
}
export interface QA { q: string; a: string; at: string }

/* ── Intelligence layer ─────────────────────────────────────────────────── */

/** LLM narration of an already-computed result. `available: false` means the numbers stand alone. */
export interface Narrative { text: string; available: boolean; warnings: string[] }
export interface ProviderStatus { status: string; reason?: string | null; source_type?: string; data?: unknown }

export interface RatioAnomaly {
  metric: string; label: string; status: "PASS" | "WARN" | "FAIL" | "SKIP"; period: string | null;
  current: number | null; historical_mean: number | null; historical_range: number[] | null;
  z_score: number | null; detail: string;
}
export interface Extended {
  sections: LedgerSection[]; coverage_pct: number; status_counts: Record<string, number>;
  advisory_risks: RiskIndicator[];
  ratio_anomalies: { overall_status: "PASS" | "WARN" | "FAIL" | "SKIP"; counts: Record<string, number>; results: RatioAnomaly[] };
  sector: { value: string; domain_inputs: Record<string, number>; input_fields: Record<string, string[]> };
}

export type Verdict5 = "ALIGNED" | "OPTIMISTIC" | "AGGRESSIVE" | "CAUTIOUS" | "OVERLY_CONSERVATIVE" | "NO_REFERENCE_DATA";
export interface ForecastResult {
  metric: string; label: string; assumption_pct: number; currency: string | null;
  references: { label: string; value_pct: number; source: string }[];
  classification: { verdict: Verdict5; reference_low: number | null; reference_high: number | null; deviation_pp: number | null; detail: string };
  drivers: string[];
  projection: { base_period: string; base_value: number; points: { period: string; value: number }[] } | null;
  external: Record<string, ProviderStatus>;
  narrative: Narrative | null;
}
export interface BenchmarkRow {
  key: string; label: string; unit: string; target: number | null; peer_median: number | null;
  peer_mean: number | null; gap: number | null; peer_count: number;
  peer_values: { ticker: string; value: number }[];
}
export interface CompetitiveResult {
  status: "OK" | "UNAVAILABLE"; reason?: string; currency?: string | null; rows: BenchmarkRow[];
  peers: { ticker: string; name: string; currency: string | null }[]; failed?: { ticker: string; reason: string }[];
  narrative?: Narrative | null;
}
export interface CreditResult { status: "OK" | "UNAVAILABLE"; reason?: string; narrative: Narrative | null }
export interface RegionMetrics {
  periods: string[]; revenue: number[]; revenue_share_pct: (number | null)[]; yoy_growth_pct: (number | null)[];
  volatility: number | null; latest_yoy_growth_pct: number | null; notable_swing: boolean;
}
export interface GeographyResult {
  status: "OK" | "UNAVAILABLE"; reason?: string; currency?: string | null;
  region_metrics: Record<string, RegionMetrics>; notable_regions: string[];
  news_status: Record<string, string>; headlines: Record<string, { title: string; source: string; publishedAt: string }[]>;
  narrative: Narrative | null; input?: Record<string, Record<string, number>>;
}
export interface GovernanceFinding {
  name: string; din: string; status: "PASS" | "WARN" | "UNAVAILABLE"; news_status: string;
  statutory_lookup: ProviderStatus;
  adverse_mention_screen: { articles_scanned: number; matches: { title: string; url?: string; matched_keywords: string[]; source?: string }[] };
}
export interface GovernanceResult {
  status: "OK" | "UNAVAILABLE"; reason?: string; overall?: "PASS" | "WARN" | "UNAVAILABLE";
  findings?: GovernanceFinding[]; narrative?: Narrative | null;
}
export interface Intelligence {
  forecast?: ForecastResult; competitive?: CompetitiveResult; credit?: CreditResult;
  geography?: GeographyResult; governance?: GovernanceResult;
}

export interface Report {
  entity: string; currency: string | null; industry: string | null; has_record: boolean;
  verdict: Verdict | null; scorecard: Scorecard | null;
  anomalies: { critical: number; warning: number; items: { field: string; period: string | null; severity: string; detail: string }[] } | null;
  trends: Trends | null; ledger: LedgerSection[]; peers: Peer[];
  peer_metrics: Record<string, { target?: number | null; peer_median?: number | null; percentile?: number | null }>;
  risk: { overall: string; fail_count: number; warn_count: number; indicators: RiskIndicator[] } | null;
  credit_report: { strengths: string[]; risks: string[]; narrative: string; disclaimer: string } | null;
  qualitative_findings: string[]; workflow_log: string[]; errors: string[];
  dscr: DscrView | null; dscr_terms: DscrTerms | null; dscr_bases: { key: string; label: string }[];
  ai: { explain: string | null; qa: QA[] };
  extended: Extended | null; intelligence: Intelligence; default_peer_tickers: string[];
}

export interface Analysis {
  id: string; status: RunStatus; stages: Stage[]; entity: string; source_label: string;
  created_at: string; finished_at: string | null; error: string | null; report?: Report;
}
export type Current = (Analysis & { has_data: boolean }) | { status: "none"; has_data: boolean };

/* ── Hooks ──────────────────────────────────────────────────────────────── */

const isActive = (s?: RunStatus | "none") => s === "queued" || s === "running";

export function useCurrentAnalysis() {
  return useQuery({
    queryKey: ["analysis", "current"],
    queryFn: () => api<Current>("/analysis/current"),
    refetchInterval: (q) => (isActive(q.state.data?.status) ? 1500 : false),
  });
}

export function useAnalysis(id: string | undefined) {
  return useQuery({
    queryKey: ["analysis", id],
    queryFn: () => api<Analysis>(`/analysis/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (isActive(q.state.data?.status) ? 1500 : false),
  });
}

export function useStartAnalysis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      try {
        return await api<Analysis>("/analysis", { method: "POST" });
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) return null; // one is already running — just follow it
        throw e;
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["analysis"] }),
  });
}

export function useDscr(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (terms: DscrTerms) => api<DscrView>(`/analysis/${id}/dscr`, { json: terms }),
    // The minimum DSCR feeds the scorecard and verdict, so reload the report.
    onSuccess: () => qc.invalidateQueries({ queryKey: ["analysis", id] }),
  });
}

/**
 * One on-demand agent call (forecast check, benchmark, geography, ...). The result is saved on the
 * analysis server-side, so the report is refetched afterwards and a reload shows it again.
 */
export function useAgent<TOut, TIn = void>(analysisId: string, path: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TIn) => api<TOut>(`/analysis/${analysisId}/${path}`, { method: "POST", json: body ?? {} }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["analysis", analysisId] }),
  });
}

/** Mongo returns naive UTC timestamps; make sure the browser reads them as UTC. */
export function parseUtc(ts: string | null | undefined): Date | null {
  if (!ts) return null;
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(ts) ? ts : `${ts}Z`);
}
