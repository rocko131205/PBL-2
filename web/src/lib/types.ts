/** Shapes returned by the API (see api/workspace.py and api/routers/ingest.py). */

export type SourceKind = "pdf" | "ticker" | "csv";

export interface SeriesPoint { period: string; value: number; display: string }

export interface MetricCard {
  field: string;
  label: string;
  period: string;
  value: number | null;
  display: string;
  change_pct: number | null;
  series: SeriesPoint[];
}

export interface ScaleOption { key: string; label: string; multiplier: number }

export interface AgentReadiness { key: string; label: string; ready: boolean }

export interface Readiness {
  missing_fields: string[];
  complete: boolean;
  skipped_agents: string[];
  agents: AgentReadiness[];
}

export interface CredibilityCheck {
  name: string;
  status: "pass" | "warn" | "fail" | "skip";
  detail: string;
  weight: number;
}

export interface Credibility {
  score: number;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  source: string;
  entity: string;
  checks: CredibilityCheck[];
}

export interface WorkspaceEmpty { loaded: false }

export interface WorkspaceLoaded {
  loaded: true;
  source: SourceKind;
  source_label: string;
  ticker: string | null;
  entity: { name: string; currency: string | null };
  fields_loaded: string[];
  scale: { applicable: boolean; multiplier: number; options: ScaleOption[] };
  cards: MetricCard[];
  preview: { field: string; period: string; value: number }[];
  readiness: Readiness;
  periods: string[];
  qualitative: string;
  supplement: { ticker: string | null; fmp: boolean; alphavantage: boolean };
  credibility: Credibility | null;
}

export type Workspace = WorkspaceEmpty | WorkspaceLoaded;
