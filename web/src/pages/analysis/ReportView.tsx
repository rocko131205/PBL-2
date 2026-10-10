import { useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertOctagon, ArrowDownUp, Download, FileText, Info, Printer, TriangleAlert } from "lucide-react";
import clsx from "clsx";
import { Alert, Button, Card } from "@/components/ui";
import { C, axis, tooltip } from "@/components/chart";
import { api } from "@/lib/api";
import type { Analysis, Factor, Report } from "@/lib/analysis";
import { parseUtc } from "@/lib/analysis";
import { formatRatio } from "@/lib/format";
import { TrendsSection, PeersSection } from "./Charts";
import { MetricsTab } from "./Ledger";
import { DscrSection } from "./Dscr";
import { AssistantSection } from "./Assistant";

/* ── Shared bits ────────────────────────────────────────────────────────── */

export function Section({ id, title, subtitle, children, right }: { id: string; title: string; subtitle?: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="text-sm text-ink-3">{subtitle}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

export const gradeTone = (g: string) =>
  ["AA", "A"].includes(g) ? "text-good" : g === "BBB" ? "text-info" : g === "BB" ? "text-watch" : g === "NR" ? "text-ink-3" : "text-risk";
export const scoreColor = (s: number) => (s >= 70 ? C.good : s >= 45 ? C.watch : C.risk);

type TabId = "overview" | "trends" | "metrics" | "peers" | "debt" | "assessment" | "assistant" | "memo" | "audit";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" }, { id: "trends", label: "Trends" }, { id: "metrics", label: "Metrics" },
  { id: "peers", label: "Peers" }, { id: "debt", label: "Debt service" }, { id: "assessment", label: "Assessment" },
  { id: "assistant", label: "AI assistant" }, { id: "memo", label: "Memo" }, { id: "audit", label: "Audit" },
];

/* ── Page ───────────────────────────────────────────────────────────────── */

export function ReportView({ analysis, report }: { analysis: Analysis; report: Report }) {
  const finished = parseUtc(analysis.finished_at);
  // The open tab lives in the URL (?tab=debt) so refresh, back/forward and shared links keep it.
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab") as TabId | null;
  const tab: TabId = TABS.some((t) => t.id === requested) ? requested! : "overview";
  const open = (id: TabId) => {
    setParams(id === "overview" ? {} : { tab: id });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Left/right arrows move between tabs, as screen-reader users expect from a tablist.
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const i = TABS.findIndex((t) => t.id === tab);
    const next = TABS[(i + (e.key === "ArrowRight" ? 1 : -1) + TABS.length) % TABS.length].id;
    open(next);
    document.getElementById(`tab-${next}`)?.focus();
  };

  return (
    <div className="space-y-6 pb-12">
      <div>
        <div className="text-xs uppercase tracking-wide text-ink-3">Financial analysis</div>
        <h1 className="text-2xl font-semibold tracking-tight">{report.entity}</h1>
        <div className="text-sm text-ink-3">
          {analysis.source_label}{report.industry ? ` · ${report.industry}` : ""}{report.currency ? ` · ${report.currency}` : ""}
          {finished ? ` · analysed ${finished.toLocaleString()}` : ""}
        </div>
      </div>

      <div role="tablist" aria-label="Report sections" onKeyDown={onKey}
        className="glass sticky top-2 z-20 -mx-1 flex gap-1 overflow-x-auto rounded-full bg-[#0b0f16]/95 p-1.5 shadow-lg shadow-black/40 no-print">
        {TABS.map((t) => {
          const active = t.id === tab;
          return (
            <button key={t.id} id={`tab-${t.id}`} role="tab" aria-selected={active} aria-controls="report-panel"
              tabIndex={active ? 0 : -1} onClick={() => open(t.id)}
              className={clsx("whitespace-nowrap rounded-full px-4 py-2 text-sm font-medium transition",
                active ? "accent-gradient text-white shadow-[0_8px_24px_-10px_#3b82f6]" : "text-ink-2 hover:bg-white/10 hover:text-ink")}>
              {t.label}
            </button>
          );
        })}
      </div>

      {report.errors.length > 0 && tab === "overview" && (
        <Alert tone="watch">
          The pipeline finished with {report.errors.length} warning{report.errors.length > 1 ? "s" : ""}, so some narrative may be partial.
          All computed figures are complete. Details are in the Audit tab.
        </Alert>
      )}

      <div id="report-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "overview" && (
          <Section id="overview" title="Overview" subtitle="Decision-support only — not a lending decision">
            {report.verdict ? <VerdictBanner report={report} /> : <Alert tone="info">Not enough financial data to grade this company yet.</Alert>}
            {report.scorecard && <ScorecardCard report={report} />}
            <Anomalies report={report} />
          </Section>
        )}

        {tab === "trends" && (
          <Section id="trends" title="Trends & forecast" subtitle="History plus a three-year revenue projection with scenarios">
            {report.trends
              ? <TrendsSection trends={report.trends} currency={report.currency} />
              : <Alert tone="info">At least two periods of revenue are needed to show trends.</Alert>}
          </Section>
        )}

        {tab === "metrics" && (
          <Section id="metrics" title="Computed metrics" subtitle="Every figure comes from the deterministic fact ledger">
            <MetricsTab report={report} />
          </Section>
        )}

        {tab === "peers" && (
          <Section id="peers" title="Peer benchmarking" subtitle="Live data from Yahoo Finance — no AI-estimated values">
            <PeersSection peers={report.peers} metrics={report.peer_metrics} />
          </Section>
        )}

        {tab === "debt" && (
          <Section id="debt" title="Debt serviceability" subtitle="DSCR across the full loan life, with stress testing">
            <DscrSection analysisId={analysis.id} report={report} />
          </Section>
        )}

        {tab === "assessment" && (
          <Section id="assessment" title="Credit assessment" subtitle="Synthesised from the computed facts">
            <Assessment report={report} />
          </Section>
        )}

        {tab === "assistant" && (
          <Section id="assistant" title="AI assistant" subtitle="Explains the computed facts — it can't change or invent a number">
            <AssistantSection analysisId={analysis.id} ai={report.ai} />
          </Section>
        )}

        {tab === "memo" && (
          <Section id="memo" title="Credit memo" subtitle="A one-page lender-style summary">
            <MemoCard analysisId={analysis.id} report={report} />
          </Section>
        )}

        {tab === "audit" && (
          <Section id="audit" title="Audit trail" subtitle="How the result was produced">
            <Audit analysisId={analysis.id} report={report} />
          </Section>
        )}
      </div>
    </div>
  );
}

/* ── Overview ───────────────────────────────────────────────────────────── */

function VerdictBanner({ report }: { report: Report }) {
  const v = report.verdict!;
  const dscrTone = v.min_dscr == null ? "" : v.min_dscr >= 1.5 ? "text-good" : v.min_dscr >= 1 ? "text-watch" : "text-risk";
  return (
    <Card className="relative overflow-hidden p-6 sm:p-8">
      <div className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full bg-brand-600/20 blur-3xl" aria-hidden />
      <div className="relative flex flex-wrap items-center gap-x-10 gap-y-6">
        <div>
          <div className="text-xs uppercase tracking-wide text-ink-3">Credit grade</div>
          <div className={clsx("text-6xl font-semibold tracking-tight", gradeTone(v.grade))}>{v.grade}</div>
          <div className="text-sm text-ink-2">{v.grade_label}</div>
        </div>
        <dl className="grid flex-1 grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3">
          <Stat label="Composite score" value={<span className="num">{v.composite.toFixed(0)}<span className="text-sm text-ink-3"> / 100</span></span>} />
          <Stat label="Est. default probability" value={v.pd_band} />
          <Stat label="Minimum DSCR" value={v.min_dscr == null ? <span className="text-sm text-ink-3">Run the loan test below</span> : <span className={clsx("num", dscrTone)}>{formatRatio(v.min_dscr)}</span>} />
        </dl>
      </div>
      {v.watch && (
        <div className="relative mt-6 flex items-start gap-2 rounded-xl bg-watch-bg px-4 py-3 text-sm text-watch">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span><b>Watch:</b> {v.watch.name.toLowerCase()} — {v.watch.note}</span>
        </div>
      )}
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="mt-1 text-xl font-semibold">{value}</dd>
    </div>
  );
}

type SortKey = "bucket" | "name" | "score" | "weight";

function ScorecardCard({ report }: { report: Report }) {
  const sc = report.scorecard!;
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "bucket", desc: false });
  const buckets = Object.entries(sc.buckets).filter(([, v]) => v != null).map(([name, score]) => ({ name, score: score as number }));
  const factors = useMemo(() => {
    const val = (f: Factor) => (sort.key === "score" ? f.score ?? -1 : sort.key === "weight" ? f.weight : sort.key === "name" ? f.name : f.bucket);
    return [...sc.factors].sort((a, b) => {
      const x = val(a), y = val(b);
      const r = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      return sort.desc ? -r : r;
    });
  }, [sc.factors, sort]);

  const th = (key: SortKey, label: string, cls = "") => (
    <th className={clsx("px-3 py-2.5 font-medium", cls)} aria-sort={sort.key === key ? (sort.desc ? "descending" : "ascending") : "none"}>
      <button className="inline-flex items-center gap-1 hover:text-ink" onClick={() => setSort({ key, desc: sort.key === key ? !sort.desc : false })}>
        {label} <ArrowDownUp className="size-3" aria-hidden />
      </button>
    </th>
  );

  return (
    <Card className="p-5 sm:p-6">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div>
          <h3 className="text-sm font-semibold">Score by area</h3>
          <p className="text-xs text-ink-3">Industry profile: {sc.industry_profile} · {(sc.covered_weight * 100).toFixed(0)}% of scorecard weight had data</p>
          <div className="mt-4 h-56" role="img" aria-label="Score by area, 0 to 100">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={buckets} layout="vertical" margin={{ left: 8, right: 16 }}>
                <XAxis type="number" domain={[0, 100]} {...axis} />
                <YAxis type="category" dataKey="name" width={110} {...axis} />
                <Tooltip {...tooltip} cursor={{ fill: "#ffffff0a" }} formatter={(v) => [`${Number(v).toFixed(0)} / 100`, "Score"]} />
                <Bar dataKey="score" radius={[0, 6, 6, 0]} barSize={16}>
                  {buckets.map((b) => <Cell key={b.name} fill={scoreColor(b.score)} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">How the grade was built</h3>
          <div className="mt-3 max-h-80 overflow-auto rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-solid text-left text-xs text-ink-3">
                <tr>{th("bucket", "Area")}{th("name", "Factor")}<th className="px-3 py-2.5 font-medium">Value</th>{th("score", "Score", "text-right")}{th("weight", "Weight", "text-right")}</tr>
              </thead>
              <tbody>
                {factors.map((f) => (
                  <tr key={f.key} className="border-t border-line/60">
                    <td className="px-3 py-2 text-ink-3">{f.bucket}</td>
                    <td className="px-3 py-2">{f.name}</td>
                    <td className="px-3 py-2 text-ink-2">{f.note || "—"}</td>
                    <td className="num px-3 py-2 text-right" style={{ color: f.score == null ? undefined : scoreColor(f.score) }}>{f.score == null ? "—" : f.score.toFixed(0)}</td>
                    <td className="num px-3 py-2 text-right text-ink-3">{f.weight.toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      {sc.notes.length > 0 && (
        <ul className="mt-5 space-y-2">
          {sc.notes.map((n) => <li key={n} className="flex gap-2 text-xs text-ink-2"><Info className="mt-0.5 size-3.5 shrink-0 text-info" aria-hidden />{n}</li>)}
        </ul>
      )}
    </Card>
  );
}

function Anomalies({ report }: { report: Report }) {
  const a = report.anomalies;
  if (!a) return null;
  if (a.items.length === 0) return <Alert tone="good">No anomalies detected — the figures are internally consistent.</Alert>;
  const tone: Record<string, string> = { critical: "bg-risk-bg text-risk", warning: "bg-watch-bg text-watch", info: "bg-info-bg text-info" };
  return (
    <Card className="p-5 sm:p-6">
      <div className="flex items-center gap-2">
        <AlertOctagon className="size-4 text-watch" aria-hidden />
        <h3 className="text-sm font-semibold">Data & risk alerts</h3>
        <span className="text-xs text-ink-3">{a.critical} critical · {a.warning} warning</span>
      </div>
      <ul className="mt-3 divide-y divide-line">
        {a.items.map((it, i) => (
          <li key={i} className="flex items-start gap-3 py-2.5 text-sm">
            <span className={clsx("mt-0.5 w-16 shrink-0 rounded-full px-2 py-0.5 text-center text-[11px] font-medium capitalize", tone[it.severity] ?? "bg-white/10 text-ink-2")}>{it.severity}</span>
            <span className="text-ink-2">{it.detail}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-ink-3">Flags for review, not verdicts. Ask the AI assistant to explain any of them.</p>
    </Card>
  );
}

/* ── Assessment / memo / audit ──────────────────────────────────────────── */

function Assessment({ report }: { report: Report }) {
  const cr = report.credit_report;
  return (
    <div className="space-y-4">
      {cr && (cr.strengths.length > 0 || cr.risks.length > 0) && (
        <div className="grid gap-4 md:grid-cols-2">
          <ListCard title="Major strengths" items={cr.strengths} tone="good" />
          <ListCard title="Major risks" items={cr.risks} tone="risk" />
        </div>
      )}
      {cr?.narrative ? (
        <Card className="p-5 sm:p-6"><h3 className="text-sm font-semibold">Assessment narrative</h3><p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-ink-2">{cr.narrative}</p></Card>
      ) : (
        <Alert tone="info">No narrative was generated — the AI model may have been unavailable. Every computed figure above is complete without it.</Alert>
      )}
      {report.qualitative_findings.length > 0 && <ListCard title="From management commentary" items={report.qualitative_findings} tone="info" />}
      {cr?.disclaimer && <p className="text-xs italic text-ink-3">{cr.disclaimer}</p>}
    </div>
  );
}

function ListCard({ title, items, tone }: { title: string; items: string[]; tone: "good" | "risk" | "info" }) {
  const dot = { good: "bg-good", risk: "bg-risk", info: "bg-info" }[tone];
  return (
    <Card className="p-5 sm:p-6">
      <h3 className="text-sm font-semibold">{title}</h3>
      {items.length === 0 ? <p className="mt-2 text-sm text-ink-3">None identified.</p> : (
        <ul className="mt-3 space-y-2">
          {items.map((t, i) => <li key={i} className="flex gap-2.5 text-sm text-ink-2"><span className={clsx("mt-2 size-1.5 shrink-0 rounded-full", dot)} aria-hidden />{t}</li>)}
        </ul>
      )}
    </Card>
  );
}

function MemoCard({ analysisId, report }: { analysisId: string; report: Report }) {
  const v = report.verdict;
  const base = `/api/analysis/${analysisId}/memo`;
  return (
    <Card className="flex flex-wrap items-center justify-between gap-4 p-5 sm:p-6">
      <div className="flex items-center gap-4">
        <span className="grid size-12 place-items-center rounded-2xl bg-brand-50"><FileText className="size-6 text-brand-700" aria-hidden /></span>
        <div>
          <div className="font-medium">Credit memo — {report.entity}</div>
          <div className="text-sm text-ink-3">
            {v ? `Grade ${v.grade} (${v.grade_label}) · PD ${v.pd_band}${v.min_dscr != null ? ` · min DSCR ${formatRatio(v.min_dscr)}` : ""}` : "Grade not available"}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <a href={base} target="_blank" rel="noopener" className="inline-flex h-11 items-center gap-2 rounded-full border border-line-strong px-5 text-sm font-medium hover:bg-white/10">
          <Printer className="size-4" aria-hidden /> Open to print
        </a>
        <a href={`${base}?download=true`} className="accent-gradient inline-flex h-11 items-center gap-2 rounded-full px-5 text-sm font-medium text-white">
          <Download className="size-4" aria-hidden /> Download
        </a>
      </div>
    </Card>
  );
}

function Audit({ analysisId, report }: { analysisId: string; report: Report }) {
  const [raw, setRaw] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const loadRaw = async () => {
    setLoading(true);
    try { setRaw(JSON.stringify(await api(`/analysis/${analysisId}/raw`), null, 2)); } finally { setLoading(false); }
  };
  return (
    <div className="space-y-3">
      <details className="glass rounded-2xl p-5">
        <summary className="cursor-pointer text-sm font-medium">Agent workflow log ({report.workflow_log.length} entries)</summary>
        <ol className="num mt-3 max-h-80 space-y-1 overflow-auto text-xs text-ink-3">{report.workflow_log.map((l, i) => <li key={i}>{l}</li>)}</ol>
        {report.errors.length > 0 && (
          <div className="mt-4"><div className="text-xs font-medium text-watch">Warnings</div>
            <ul className="num mt-1 space-y-1 text-xs text-ink-3">{report.errors.map((e, i) => <li key={i}>{e}</li>)}</ul></div>
        )}
      </details>
      <details className="glass rounded-2xl p-5" onToggle={(e) => { if ((e.target as HTMLDetailsElement).open && raw == null) loadRaw(); }}>
        <summary className="cursor-pointer text-sm font-medium">Raw computed data (JSON)</summary>
        {loading && <p className="mt-3 text-xs text-ink-3">Loading…</p>}
        {raw && <pre className="num mt-3 max-h-[28rem] overflow-auto rounded-xl bg-black/40 p-4 text-[11px] text-ink-2">{raw}</pre>}
        {raw && <Button variant="secondary" className="mt-3 h-9" onClick={() => navigator.clipboard?.writeText(raw)}>Copy JSON</Button>}
      </details>
    </div>
  );
}
