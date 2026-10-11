import { useState, type FormEvent } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Calculator, Info, Play, Users } from "lucide-react";
import clsx from "clsx";
import { Alert, Button, Card, Field, SelectField } from "@/components/ui";
import { NarrativeCard, StatusBadge } from "@/components/StatusBadge";
import { C, axis, compact, tooltip } from "@/components/chart";
import { ApiError } from "@/lib/api";
import { useAgent } from "@/lib/analysis";
import type { BenchmarkRow, CompetitiveResult, CreditResult, ForecastResult, LedgerRow, Report, Verdict5 } from "@/lib/analysis";
import { formatMoney, formatPeriod } from "@/lib/format";

const errorText = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
const num = (s: string) => Number(s.replace(/,/g, "").trim());

/** Shared value formatter for benchmark-style numbers. */
function fmt(v: number | null | undefined, unit: string, ccy: string | null): string {
  if (v == null) return "—";
  if (unit === "%") return `${v.toFixed(2)}%`;
  if (unit === "ratio") return `${v.toFixed(2)}x`;
  if (unit === "absolute") return formatMoney(v, ccy);
  return v.toFixed(2);
}

/* ── Risk & alerts ──────────────────────────────────────────────────────── */

const TONE = { PASS: "text-good", WARN: "text-watch", FAIL: "text-risk", SKIP: "text-ink-3" } as const;
const RANK = { FAIL: 0, WARN: 1, PASS: 2, SKIP: 3 } as const;

export function RiskAlertsSection({ report }: { report: Report }) {
  const ext = report.extended;
  if (!ext) return <Alert tone="info">Risk alerts need a financial record to work from.</Alert>;
  const checks = [...ext.advisory_risks].sort((a, b) => RANK[a.status] - RANK[b.status]);
  const scan = ext.ratio_anomalies;
  const results = [...scan.results].sort((a, b) => RANK[a.status] - RANK[b.status]);
  const concerns = checks.filter((c) => c.status === "FAIL").length + scan.counts.FAIL;
  const watch = checks.filter((c) => c.status === "WARN").length + scan.counts.WARN;

  return (
    <div className="space-y-5">
      <Card className="flex flex-wrap items-center gap-x-10 gap-y-4 p-5">
        <div>
          <div className="text-xs text-ink-3">Advisory alerts</div>
          <div className="mt-1 flex items-baseline gap-5">
            <span className={clsx("num text-3xl font-semibold", concerns ? "text-risk" : "text-ink-3")}>{concerns}<span className="ml-1.5 text-xs font-normal text-ink-3">concerns</span></span>
            <span className={clsx("num text-3xl font-semibold", watch ? "text-watch" : "text-ink-3")}>{watch}<span className="ml-1.5 text-xs font-normal text-ink-3">to watch</span></span>
          </div>
        </div>
        <p className="max-w-xl text-xs leading-relaxed text-ink-3">
          A second, independent view alongside the credit grade. These alerts are for an analyst to review and <b className="text-ink-2">do not change the grade or the overall risk level</b>.
        </p>
      </Card>

      <div>
        <h3 className="mb-3 text-sm font-semibold">Trend checks</h3>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {checks.map((c) => (
            <Card key={c.name} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <span className="text-sm font-medium">{c.name}</span>
                <StatusBadge status={c.status} />
              </div>
              <p className="mt-2 text-xs leading-relaxed text-ink-3">{c.detail}</p>
            </Card>
          ))}
        </div>
      </div>

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line p-4">
          <div>
            <h3 className="text-sm font-semibold">Against the company's own history</h3>
            <p className="text-xs text-ink-3">Flags a ratio that has broken sharply from its own past range, even if it still looks healthy in absolute terms.</p>
          </div>
          <StatusBadge status={scan.overall_status} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-ink-3">
              <tr className="border-b border-line">
                <th className="px-4 py-2.5 font-medium">Ratio</th><th className="px-4 py-2.5 text-right font-medium">Latest</th>
                <th className="px-4 py-2.5 text-right font-medium">Own average</th><th className="px-4 py-2.5 text-right font-medium">Range</th>
                <th className="px-4 py-2.5 text-right font-medium">Std-devs away</th><th className="px-4 py-2.5 font-medium">Result</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.metric} className="border-b border-line/60 last:border-0" title={r.detail}>
                  <td className="px-4 py-3">{r.label}<div className="text-[11px] text-ink-3">{r.period ? formatPeriod(r.period) : r.detail}</div></td>
                  <td className="num px-4 py-3 text-right">{r.current == null ? "—" : r.current.toFixed(2)}</td>
                  <td className="num px-4 py-3 text-right text-ink-2">{r.historical_mean == null ? "—" : r.historical_mean.toFixed(2)}</td>
                  <td className="num px-4 py-3 text-right text-ink-3">{r.historical_range ? `${r.historical_range[0].toFixed(2)} – ${r.historical_range[1].toFixed(2)}` : "—"}</td>
                  <td className={clsx("num px-4 py-3 text-right", TONE[r.status])}>{r.z_score == null ? "—" : r.z_score.toFixed(1)}</td>
                  <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="flex gap-2 border-t border-line p-4 text-xs text-ink-3">
          <Info className="mt-0.5 size-3.5 shrink-0 text-info" aria-hidden />
          Needs at least four periods. With a short, smooth history even a modest move can look large in standard deviations, so read a flag as "worth a look", not as a verdict.
        </p>
      </Card>
    </div>
  );
}

/* ── Forecast assumption check ──────────────────────────────────────────── */

const VERDICT: Record<Verdict5, { cls: string; label: string; help: string }> = {
  ALIGNED: { cls: "bg-good-bg text-good", label: "Aligned", help: "Within the range the company's own history and guidance support." },
  OPTIMISTIC: { cls: "bg-watch-bg text-watch", label: "Optimistic", help: "Somewhat above the supported range." },
  AGGRESSIVE: { cls: "bg-risk-bg text-risk", label: "Aggressive", help: "Well above anything the references support." },
  CAUTIOUS: { cls: "bg-watch-bg text-watch", label: "Cautious", help: "Somewhat below the supported range." },
  OVERLY_CONSERVATIVE: { cls: "bg-risk-bg text-risk", label: "Overly conservative", help: "Well below the supported range." },
  NO_REFERENCE_DATA: { cls: "bg-white/10 text-ink-3", label: "No reference data", help: "Nothing to compare the assumption against." },
};

export function ForecastSection({ analysisId, report }: { analysisId: string; report: Report }) {
  const run = useAgent<ForecastResult, Record<string, unknown>>(analysisId, "forecast/validate");
  const [f, setF] = useState({ metric: "revenue", assumption: "", periods: "3", gLow: "", gHigh: "", bench: "" });
  const [local, setLocal] = useState("");
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const result = run.data ?? report.intelligence.forecast;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const a = num(f.assumption);
    if (f.assumption.trim() === "" || Number.isNaN(a)) return setLocal("Enter the growth rate you want to test, e.g. 12.");
    if (a < -100 || a > 500) return setLocal("The growth rate must be between -100 and 500.");
    const opt = (s: string) => (s.trim() === "" ? null : num(s));
    const [lo, hi, bm] = [opt(f.gLow), opt(f.gHigh), opt(f.bench)];
    if ([lo, hi, bm].some((v) => v !== null && Number.isNaN(v))) return setLocal("Please enter numbers only.");
    if (lo !== null && hi !== null && lo > hi) return setLocal("Guidance low can't be above guidance high.");
    setLocal("");
    run.mutate({ metric: f.metric, assumption_pct: a, periods_ahead: Math.round(num(f.periods) || 3), guidance_low: lo, guidance_high: hi, sector_benchmark_pct: bm });
  };

  return (
    <div className="space-y-4">
      <Card className="p-5 sm:p-6">
        <p className="text-sm text-ink-2">
          Enter the annual growth you expect. Python compares it with what the company's own history, management guidance and any benchmark you add actually support, and
          gives a verdict. The AI then explains the reasoning; it <b className="text-ink">cannot change the verdict</b> or the projection.
        </p>
        <form onSubmit={submit} noValidate className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <SelectField label="What are you forecasting?" value={f.metric} onChange={set("metric")}>
            <option value="revenue">Revenue</option><option value="ebitda">EBITDA</option><option value="pat">Net profit (PAT)</option>
          </SelectField>
          <Field label="Your assumed growth (% a year)" inputMode="decimal" value={f.assumption} onChange={set("assumption")} placeholder="e.g. 12" required />
          <Field label="Years to project" inputMode="numeric" value={f.periods} onChange={set("periods")} />
          <Field label="Management guidance, low (%)" inputMode="decimal" value={f.gLow} onChange={set("gLow")} hint="Optional" />
          <Field label="Management guidance, high (%)" inputMode="decimal" value={f.gHigh} onChange={set("gHigh")} hint="Optional" />
          <Field label="Sector / peer benchmark (%)" inputMode="decimal" value={f.bench} onChange={set("bench")} hint="Optional" />
          <div className="space-y-3 sm:col-span-2 lg:col-span-3">
            {local && <Alert tone="watch">{local}</Alert>}
            {run.isError && <Alert tone="risk">{errorText(run.error)}</Alert>}
            <Button type="submit" loading={run.isPending}><Calculator className="size-4" aria-hidden /> Check this assumption</Button>
          </div>
        </form>
      </Card>
      {result && <ForecastResultView r={result} />}
    </div>
  );
}

function ForecastResultView({ r }: { r: ForecastResult }) {
  const v = VERDICT[r.classification.verdict];
  const c = r.classification;
  const chart = r.projection ? [{ period: r.projection.base_period, value: r.projection.base_value, base: true }, ...r.projection.points.map((p) => ({ ...p, base: false }))] : [];
  return (
    <>
      <Card className="relative overflow-hidden p-5 sm:p-6">
        <div className="flex flex-wrap items-center gap-x-10 gap-y-4">
          <div>
            <div className="text-xs uppercase tracking-wide text-ink-3">{r.label}: {r.assumption_pct.toFixed(1)}% a year</div>
            <span className={clsx("mt-2 inline-block rounded-full px-4 py-1.5 text-lg font-semibold", v.cls)}>{v.label}</span>
            <p className="mt-1.5 text-xs text-ink-3">{v.help}</p>
          </div>
          {c.reference_low != null && c.reference_high != null && (
            <dl className="grid grid-cols-2 gap-x-8 gap-y-2 sm:grid-cols-3">
              <div><dt className="text-xs text-ink-3">Supported range</dt><dd className="num text-lg font-semibold">{c.reference_low.toFixed(1)}% – {c.reference_high.toFixed(1)}%</dd></div>
              <div><dt className="text-xs text-ink-3">Your assumption</dt><dd className="num text-lg font-semibold">{r.assumption_pct.toFixed(1)}%</dd></div>
              <div><dt className="text-xs text-ink-3">Outside range by</dt><dd className="num text-lg font-semibold">{(c.deviation_pp ?? 0).toFixed(1)} pp</dd></div>
            </dl>
          )}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="text-sm font-semibold">What it was compared with</h3>
          {r.references.length === 0 ? (
            <p className="mt-2 text-sm text-ink-3">No reference points were available. Add management guidance or a benchmark above, or load more history.</p>
          ) : (
            <ul className="mt-3 divide-y divide-line">
              {r.references.map((x) => (
                <li key={x.label} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="text-ink-2">{x.label}<span className="ml-2 text-[11px] text-ink-3">{x.source.replace(/_/g, " ")}</span></span>
                  <span className="num font-medium">{x.value_pct.toFixed(2)}%</span>
                </li>
              ))}
            </ul>
          )}
          {r.drivers.length > 0 && (
            <div className="mt-4"><h4 className="text-xs uppercase tracking-wide text-ink-3">Historical pattern</h4>
              <ul className="mt-1.5 space-y-1 text-sm text-ink-2">{r.drivers.map((d) => <li key={d}>• {d}</li>)}</ul></div>
          )}
          <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-ink-3">
            {Object.entries(r.external).map(([k, p]) => (
              <span key={k} className="inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5" title={p.reason ?? undefined}>
                {k.replace(/_/g, " ")} <StatusBadge status={p.status === "OK" ? "OK" : p.status} />
              </span>
            ))}
          </div>
        </Card>

        {r.projection && (
          <Card className="p-5">
            <h3 className="text-sm font-semibold">Projection at {r.assumption_pct.toFixed(1)}% a year</h3>
            <div className="mt-3 h-52" role="img" aria-label="Projected values at the assumed growth rate">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chart} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={C.grid} vertical={false} />
                  <XAxis dataKey="period" {...axis} tickFormatter={formatPeriod} />
                  <YAxis width={52} {...axis} tickFormatter={(x) => compact.format(x)} />
                  <Tooltip {...tooltip} formatter={(x) => [formatMoney(Number(x), r.currency), r.label]} labelFormatter={(l) => formatPeriod(String(l))} />
                  <Line type="monotone" dataKey="value" stroke={C.accentStrong} strokeWidth={2.5} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <table className="mt-2 w-full text-sm">
              <tbody>
                <tr className="border-b border-line/60 text-ink-3"><td className="py-1.5">{formatPeriod(r.projection.base_period)} (actual)</td><td className="num py-1.5 text-right">{formatMoney(r.projection.base_value, r.currency)}</td></tr>
                {r.projection.points.map((p) => (
                  <tr key={p.period} className="border-b border-line/60 last:border-0"><td className="py-1.5">{formatPeriod(p.period)}</td><td className="num py-1.5 text-right">{formatMoney(p.value, r.currency)}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-ink-3">Straight compounding of your assumption; it is not a prediction.</p>
          </Card>
        )}
      </div>
      <NarrativeCard narrative={r.narrative} title="Why this verdict" />
    </>
  );
}

/* ── Competitive benchmark (lives inside the Peers tab) ─────────────────── */

const LOWER_IS_BETTER = new Set(["debt_to_equity"]);

export function CompetitiveCard({ analysisId, report }: { analysisId: string; report: Report }) {
  const run = useAgent<CompetitiveResult, { tickers: string[] }>(analysisId, "competitive");
  const [tickers, setTickers] = useState(report.default_peer_tickers.join(", "));
  const [local, setLocal] = useState("");
  const result = run.data ?? report.intelligence.competitive;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const list = tickers.split(/[,\s]+/).map((t) => t.trim().toUpperCase()).filter(Boolean);
    if (list.length > 5) return setLocal("Compare against up to 5 peers at a time.");
    if (list.some((t) => !/^[A-Z0-9][A-Z0-9.\-]{0,14}$/.test(t))) return setLocal("Use Yahoo Finance ticker symbols, e.g. INFY.NS or MSFT.");
    setLocal("");
    run.mutate({ tickers: list });
  };

  return (
    <div className="mt-8 space-y-4">
      <div>
        <h3 className="text-base font-semibold tracking-tight">Full peer benchmark</h3>
        <p className="text-sm text-ink-3">Ten metrics against real peer data run through the same engines as this company. Leave the list as is to use the peers found above.</p>
      </div>
      <Card className="p-5">
        <form onSubmit={submit} noValidate className="flex flex-wrap items-end gap-3">
          <div className="min-w-[16rem] flex-1">
            <Field label="Peer tickers (comma separated)" value={tickers} onChange={(e) => setTickers(e.target.value)} placeholder="e.g. INFY.NS, WIPRO.NS" />
          </div>
          <Button type="submit" loading={run.isPending}><Users className="size-4" aria-hidden /> Run benchmark</Button>
        </form>
        {local && <div className="mt-3"><Alert tone="watch">{local}</Alert></div>}
        {run.isError && <div className="mt-3"><Alert tone="risk">{errorText(run.error)}</Alert></div>}
        {run.isPending && <p className="mt-3 text-xs text-ink-3">Fetching peer financials. This can take a little while.</p>}
      </Card>
      {result && result.status === "UNAVAILABLE" && <Alert tone="watch">{result.reason}{result.failed?.length ? ` (${result.failed.map((f) => f.ticker).join(", ")} couldn't be fetched)` : ""}</Alert>}
      {result?.status === "OK" && <BenchmarkTable result={result} />}
      {result?.status === "OK" && <NarrativeCard narrative={result.narrative} title="How the company compares" />}
    </div>
  );
}

function BenchmarkTable({ result }: { result: CompetitiveResult }) {
  const ccy = result.currency ?? null;
  const tone = (r: BenchmarkRow) => {
    if (r.gap == null) return "text-ink-3";
    const good = LOWER_IS_BETTER.has(r.key) ? r.gap < 0 : r.gap > 0;
    return r.gap === 0 ? "text-ink-2" : good ? "text-good" : "text-risk";
  };
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-ink-3">
            <tr className="border-b border-line">
              <th className="px-4 py-3 font-medium">Metric</th><th className="px-4 py-3 text-right font-medium">Company</th>
              <th className="px-4 py-3 text-right font-medium">Peer median</th><th className="px-4 py-3 text-right font-medium">Gap</th>
              <th className="px-4 py-3 text-right font-medium">Peers</th>
            </tr>
          </thead>
          <tbody>
            {result.rows.map((r) => (
              <tr key={r.key} className="border-b border-line/60 last:border-0">
                <td className="px-4 py-3">{r.label}</td>
                <td className="num px-4 py-3 text-right font-medium">{fmt(r.target, r.unit, ccy)}</td>
                <td className="num px-4 py-3 text-right text-ink-2">{fmt(r.peer_median, r.unit, ccy)}</td>
                <td className={clsx("num px-4 py-3 text-right", tone(r))}>{r.gap == null ? "—" : `${r.gap > 0 ? "+" : ""}${fmt(r.gap, r.unit, ccy)}`}</td>
                <td className="num px-4 py-3 text-right text-ink-3">{r.peer_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="border-t border-line p-4 text-xs text-ink-3">
        Compared with {result.peers.map((p) => p.name).join(", ")}.
        {result.failed && result.failed.length > 0 && <> Couldn't fetch {result.failed.map((f) => f.ticker).join(", ")}.</>}
        {" "}Absolute amounts are compared only between companies reporting in the same currency. Green is better than the peer median, red is worse.
      </p>
    </Card>
  );
}

/* ── Working-capital credit (Tandon Method II) ──────────────────────────── */

export function CreditSection({ analysisId, report }: { analysisId: string; report: Report }) {
  const run = useAgent<CreditResult>(analysisId, "credit/narrate");
  const section = report.extended?.sections.find((s) => s.category === "credit");
  const result = run.data ?? report.intelligence.credit;
  if (!section) return <Alert tone="info">A working-capital assessment needs current assets and current liabilities, which weren't in this data.</Alert>;

  return (
    <div className="space-y-4">
      <Alert tone="watch">
        <b>These are estimates, not a bank decision.</b> Estimated MPBF (Tandon Method II) is worked out from the balance sheet alone. Drawing Power needs the bank's margin percentages and stock and receivables ageing from a sanction letter, so it is never estimated here.
      </Alert>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {section.rows.map((r) => <CreditTile key={r.metric} row={r} />)}
      </div>
      <Card className="flex flex-wrap items-center justify-between gap-3 p-5">
        <p className="max-w-xl text-sm text-ink-2">Ask the AI to explain this position and what the estimate can and can't be used for.</p>
        <Button variant="secondary" onClick={() => run.mutate(undefined)} loading={run.isPending}><Play className="size-4" aria-hidden /> {result?.narrative ? "Explain again" : "Explain this"}</Button>
      </Card>
      {run.isError && <Alert tone="risk">{errorText(run.error)}</Alert>}
      {result?.status === "OK" && <NarrativeCard narrative={result.narrative} title="Working-capital position" />}
    </div>
  );
}

function CreditTile({ row }: { row: LedgerRow }) {
  const gap = row.value == null;
  return (
    <Card className="flex min-h-[8rem] flex-col p-4" >
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm text-ink-2">{row.name}</span>
        <StatusBadge status={row.status} />
      </div>
      <div className={clsx("num mt-auto pt-3 font-semibold tracking-tight", gap ? "text-sm text-ink-3" : "text-2xl")}>{row.display}</div>
      {(row.note || (gap && row.formula)) && <p className="mt-2 line-clamp-4 text-[11px] leading-relaxed text-ink-3" title={row.note ?? undefined}>{row.note ?? row.formula}</p>}
      {!gap && row.period && <div className="mt-1 text-[11px] text-ink-3">{formatPeriod(row.period)}</div>}
    </Card>
  );
}
