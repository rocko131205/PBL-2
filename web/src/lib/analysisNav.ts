import { BarChart3, FileText, Gauge, Landmark, Sparkles, TriangleAlert, type LucideIcon } from "lucide-react";

/** Every page of the Analysis report. The open one lives in the URL (?tab=...). */
export type TabId = "overview" | "trends" | "metrics" | "alerts" | "peers" | "forecast" | "debt" | "credit" | "geography"
  | "governance" | "assessment" | "assistant" | "memo" | "audit";

export interface NavLeaf { id: TabId; label: string }
/** A top-level entry is either a page (`tab`) or an accordion group (`children`). */
export interface NavNode { key: string; label: string; Icon: LucideIcon; tab?: TabId; children?: NavLeaf[] }

/** The sidebar's Analysis submenu, and the single source for breadcrumbs and valid ?tab= values. */
export const ANALYSIS_NAV: NavNode[] = [
  { key: "overview", label: "Overview", Icon: Gauge, tab: "overview" },
  { key: "financials", label: "Financials", Icon: BarChart3, children: [
    { id: "metrics", label: "Metrics" },
    { id: "trends", label: "Trends" },
    { id: "credit", label: "Working Capital" },
    { id: "debt", label: "Debt Service" },
  ] },
  { key: "credit-group", label: "Credit", Icon: Landmark, children: [
    { id: "assessment", label: "Credit Grade" },
    { id: "forecast", label: "Forecast Check" },
    { id: "peers", label: "Peers" },
  ] },
  { key: "risk", label: "Risk & Alerts", Icon: TriangleAlert, children: [
    { id: "alerts", label: "Risk Analysis" },
    { id: "geography", label: "Geography" },
    { id: "governance", label: "Governance" },
  ] },
  { key: "assistant", label: "AI Assistant", Icon: Sparkles, tab: "assistant" },
  { key: "reports", label: "Reports", Icon: FileText, children: [
    { id: "memo", label: "Memo" },
    { id: "audit", label: "Audit Trail" },
  ] },
];

export const ALL_TABS: NavLeaf[] = ANALYSIS_NAV.flatMap((n) => (n.tab ? [{ id: n.tab, label: n.label }] : n.children ?? []));

export const analysisHref = (id: TabId) => (id === "overview" ? "/analysis" : `/analysis?tab=${id}`);

/** The tab named by a query string, falling back to Overview for anything unknown. */
export function tabFromSearch(search: string): TabId {
  const t = new URLSearchParams(search).get("tab");
  return ALL_TABS.find((x) => x.id === t)?.id ?? "overview";
}

/** The group node containing a tab, if it lives in one. */
export const groupOf = (id: TabId): NavNode | undefined => ANALYSIS_NAV.find((n) => n.children?.some((c) => c.id === id));

/** "Analysis › Financials › Metrics" */
export function breadcrumb(id: TabId): string[] {
  const group = groupOf(id);
  const label = ALL_TABS.find((t) => t.id === id)?.label ?? "Overview";
  return group ? ["Analysis", group.label, label] : ["Analysis", label];
}
