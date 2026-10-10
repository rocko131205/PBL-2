import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronRight, Sigma } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui";
import { Drawer } from "@/components/Drawer";
import { formatPeriod } from "@/lib/format";
import type { LedgerRow, Report, RiskIndicator } from "@/lib/analysis";

/* Signal styling shared by tiles, chips and the detail drawer. */
const SIGNAL = {
  FAIL: { dot: "bg-risk", text: "text-risk", pill: "bg-risk-bg text-risk", label: "Concern" },
  WARN: { dot: "bg-watch", text: "text-watch", pill: "bg-watch-bg text-watch", label: "Watch" },
  PASS: { dot: "bg-good", text: "text-good", pill: "bg-good-bg text-good", label: "Healthy" },
  NONE: { dot: "bg-white/25", text: "text-ink", pill: "bg-white/10 text-ink-3", label: "No threshold" },
} as const;
type SignalKey = keyof typeof SIGNAL;
const keyOf = (s: string | null | undefined): SignalKey => (s === "FAIL" || s === "WARN" || s === "PASS" ? s : "NONE");
const RANK: Record<SignalKey, number> = { FAIL: 0, WARN: 1, PASS: 2, NONE: 3 };

/** The worst signal in a group decides the dot on its category chip. */
const worst = (signals: (string | null | undefined)[]): SignalKey =>
  signals.map(keyOf).sort((a, b) => RANK[a] - RANK[b])[0] ?? "NONE";

type Category = { id: string; label: string; count: number; worst: SignalKey };

export function MetricsTab({ report }: { report: Report }) {
  const risk = report.risk;
  const categories: Category[] = [
    ...(risk ? [{ id: "risk", label: "Risk signals", count: risk.indicators.length, worst: worst(risk.indicators.map((i) => i.status)) }] : []),
    ...report.ledger.map((s) => ({ id: s.category, label: s.title, count: s.rows.length, worst: worst(s.rows.map((r) => r.signal)) })),
  ];

  // Sub-category is kept in the URL too (?tab=metrics&cat=liquidity).
  const [params, setParams] = useSearchParams();
  const requested = params.get("cat");
  const active = categories.find((c) => c.id === requested)?.id ?? categories[0]?.id;
  const choose = (id: string) => setParams((p) => { const n = new URLSearchParams(p); n.set("cat", id); return n; }, { replace: true });

  const [detail, setDetail] = useState<LedgerRow | null>(null);

  if (categories.length === 0) return <Card className="p-6 text-sm text-ink-3">No metrics could be computed from this data.</Card>;
  const section = report.ledger.find((s) => s.category === active);

  return (
    <div className="space-y-5">
      {risk && <RiskSummary risk={risk} onOpen={() => choose("risk")} />}

      <div role="tablist" aria-label="Metric categories" className="flex flex-wrap gap-2">
        {categories.map((c) => (
          <button key={c.id} role="tab" aria-selected={c.id === active} onClick={() => choose(c.id)}
            className={clsx("inline-flex items-center gap-2 rounded-full border px-3.5 py-2 text-sm font-medium transition",
              c.id === active ? "border-brand-600 bg-brand-50 text-ink" : "border-line-strong text-ink-2 hover:bg-white/[0.06] hover:text-ink")}>
            <span className={clsx("size-2 rounded-full", SIGNAL[c.worst].dot)} aria-hidden />
            {c.label}
            <span className="num rounded-full bg-white/10 px-1.5 text-xs text-ink-3">{c.count}</span>
          </button>
        ))}
      </div>

      {active === "risk" && risk ? (
        <IndicatorGrid indicators={risk.indicators} />
      ) : section ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {[...section.rows]
              .sort((a, b) => RANK[keyOf(a.signal)] - RANK[keyOf(b.signal)])
              .map((r) => <MetricTile key={r.metric} row={r} onOpen={() => setDetail(r)} />)}
          </div>
          <p className="text-xs text-ink-3">Concerns and watch items are listed first. Select a metric for its meaning and formula.</p>
        </>
      ) : null}

      <Drawer open={!!detail} title={detail?.name ?? ""} onClose={() => setDetail(null)}>
        {detail && <MetricDetail row={detail} />}
      </Drawer>
    </div>
  );
}

/* ── Pieces ─────────────────────────────────────────────────────────────── */

function RiskSummary({ risk, onOpen }: { risk: NonNullable<Report["risk"]>; onOpen: () => void }) {
  const overall = risk.overall === "LOW" ? SIGNAL.PASS : risk.overall === "MODERATE" ? SIGNAL.WARN : SIGNAL.FAIL;
  const healthy = risk.indicators.filter((i) => i.status === "PASS").length;
  return (
    <Card className="flex flex-wrap items-center gap-x-8 gap-y-4 p-5">
      <div>
        <div className="text-xs text-ink-3">Overall risk</div>
        <span className={clsx("mt-1 inline-block rounded-full px-3 py-1 text-sm font-semibold", overall.pill)}>{risk.overall}</span>
      </div>
      <dl className="flex flex-wrap gap-6">
        <Count label="Concerns" value={risk.fail_count} cls="text-risk" />
        <Count label="Watch" value={risk.warn_count} cls="text-watch" />
        <Count label="Healthy" value={healthy} cls="text-good" />
      </dl>
      <button onClick={onOpen} className="ml-auto inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
        View all {risk.indicators.length} indicators <ChevronRight className="size-4" aria-hidden />
      </button>
    </Card>
  );
}

function Count({ label, value, cls }: { label: string; value: number; cls: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className={clsx("num text-2xl font-semibold", value === 0 ? "text-ink-3" : cls)}>{value}</dd>
    </div>
  );
}

function MetricTile({ row, onOpen }: { row: LedgerRow; onOpen: () => void }) {
  const s = SIGNAL[keyOf(row.signal)];
  const missing = row.value == null;
  return (
    <button onClick={onOpen}
      className="glass group flex min-h-[7.5rem] flex-col rounded-2xl p-4 text-left transition hover:border-brand-600/60 hover:bg-white/[0.06]">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm text-ink-2">{row.name}</span>
        <ChevronRight className="size-4 shrink-0 text-ink-3 opacity-0 transition group-hover:opacity-100" aria-hidden />
      </div>
      <div className={clsx("num mt-auto pt-3 font-semibold tracking-tight", missing ? "text-base text-ink-3" : clsx("text-2xl", s.text))}>{row.display}</div>
      {!missing && row.signal && (
        <span className={clsx("mt-2 w-fit rounded-full px-2 py-0.5 text-[11px] font-medium", s.pill)}>{s.label}</span>
      )}
    </button>
  );
}

function MetricDetail({ row }: { row: LedgerRow }) {
  const s = SIGNAL[keyOf(row.signal)];
  return (
    <div className="space-y-6">
      <div>
        <div className={clsx("num text-4xl font-semibold", row.value == null ? "text-ink-3" : s.text)}>{row.display}</div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span className={clsx("rounded-full px-2.5 py-0.5 text-xs font-medium", s.pill)}>{s.label}</span>
          {row.period && <span className="text-ink-3">{formatPeriod(row.period)}</span>}
        </div>
      </div>
      {row.meaning && (
        <section><h3 className="text-xs uppercase tracking-wide text-ink-3">What it means</h3><p className="mt-1.5 text-sm leading-relaxed text-ink-2">{row.meaning}</p></section>
      )}
      {row.signal_detail && (
        <section><h3 className="text-xs uppercase tracking-wide text-ink-3">Why this signal</h3><p className="mt-1.5 text-sm leading-relaxed text-ink-2">{row.signal_detail}</p></section>
      )}
      {row.formula && (
        <section>
          <h3 className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-ink-3"><Sigma className="size-3.5" aria-hidden /> Formula</h3>
          <code className="num mt-1.5 block rounded-xl bg-black/40 p-3 text-sm text-ink-2">{row.formula}</code>
        </section>
      )}
      <p className="text-xs text-ink-3">Computed deterministically from the statement data — the AI never sets this value.</p>
    </div>
  );
}

function IndicatorGrid({ indicators }: { indicators: RiskIndicator[] }) {
  const sorted = [...indicators].sort((a, b) => RANK[keyOf(a.status)] - RANK[keyOf(b.status)]);
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {sorted.map((i) => {
        const s = SIGNAL[keyOf(i.status)];
        return (
          <Card key={i.name} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <span className="text-sm font-medium">{i.name}</span>
              <span className={clsx("shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium", i.status === "SKIP" ? SIGNAL.NONE.pill : s.pill)}>
                {i.status === "SKIP" ? "Skipped" : s.label}
              </span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-ink-3">{i.detail}</p>
            <div className="mt-2 text-[11px] capitalize text-ink-3">{i.category.replace(/_/g, " ")}</div>
          </Card>
        );
      })}
    </div>
  );
}
