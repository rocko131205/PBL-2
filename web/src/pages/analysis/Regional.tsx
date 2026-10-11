import { useState, type FormEvent } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { FileSearch, Globe2, Plus, ShieldQuestion, Trash2, UserRound } from "lucide-react";
import clsx from "clsx";
import { Alert, Button, Card, Field } from "@/components/ui";
import { NarrativeCard, StatusBadge } from "@/components/StatusBadge";
import { C, axis, tooltip } from "@/components/chart";
import { api, ApiError } from "@/lib/api";
import { useAgent } from "@/lib/analysis";
import type { GeographyResult, GovernanceResult, Report } from "@/lib/analysis";
import { formatMoney, formatPeriod } from "@/lib/format";

const errorText = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
const PERIOD_RE = /^\d{4}-(FY|Q[1-4])$/;

/* ── Geography ──────────────────────────────────────────────────────────── */

interface Row { region: string; values: Record<string, string> }

export function GeographySection({ analysisId, report }: { analysisId: string; report: Report }) {
  const run = useAgent<GeographyResult, { segments: Record<string, Record<string, number>> }>(analysisId, "geography");
  const saved = report.intelligence.geography;
  const result = run.data ?? saved;

  // Default to the company's two latest reported years so the first thing you type lines up with the statements.
  const revenuePeriods = (report.trends?.revenue.rows ?? []).filter((r) => r.history != null).map((r) => r.period);
  const [periods, setPeriods] = useState<string[]>(() => {
    const fromSaved = saved?.input ? [...new Set(Object.values(saved.input).flatMap((s) => Object.keys(s)))].sort() : [];
    return fromSaved.length ? fromSaved : revenuePeriods.slice(-2);
  });
  const [periodDraft, setPeriodDraft] = useState("");
  const [rows, setRows] = useState<Row[]>(() => {
    if (saved?.input) return Object.entries(saved.input).map(([region, s]) => ({ region, values: Object.fromEntries(Object.entries(s).map(([p, v]) => [p, String(v)])) }));
    return [{ region: "", values: {} }, { region: "", values: {} }];
  });
  const [text, setText] = useState("");
  const [extractPeriod, setExtractPeriod] = useState(revenuePeriods.at(-1) ?? "");
  const [msg, setMsg] = useState<{ tone: "watch" | "info"; text: string } | null>(null);
  const [extracting, setExtracting] = useState(false);

  const addPeriod = () => {
    const p = periodDraft.trim().toUpperCase();
    if (!PERIOD_RE.test(p)) return setMsg({ tone: "watch", text: "Use a period like 2024-FY or 2024-Q2." });
    if (periods.length >= 10) return setMsg({ tone: "watch", text: "Up to 10 periods." });
    if (!periods.includes(p)) setPeriods([...periods, p].sort());
    setPeriodDraft(""); setMsg(null);
  };
  const setCell = (i: number, p: string, v: string) => setRows(rows.map((r, j) => (j === i ? { ...r, values: { ...r.values, [p]: v } } : r)));

  const extract = async () => {
    const p = extractPeriod.trim().toUpperCase();
    if (!PERIOD_RE.test(p)) return setMsg({ tone: "watch", text: "Pick the period this note describes, e.g. 2024-FY." });
    setExtracting(true); setMsg(null);
    try {
      const r = await api<{ segments: Record<string, Record<string, number>> }>(`/analysis/${analysisId}/geography/extract`, { json: { text, period: p } });
      const found = Object.entries(r.segments);
      if (found.length === 0) return setMsg({ tone: "info", text: "Nothing recognisable was found. Enter the regions by hand below." });
      if (!periods.includes(p)) setPeriods([...periods, p].sort());
      setRows((prev) => {
        const next = prev.filter((x) => x.region.trim());
        for (const [region, series] of found) {
          const hit = next.find((x) => x.region.toLowerCase() === region.toLowerCase());
          if (hit) hit.values = { ...hit.values, [p]: String(series[p]) };
          else next.push({ region, values: { [p]: String(series[p]) } });
        }
        return [...next];
      });
      setMsg({ tone: "info", text: `Found ${found.length} region${found.length > 1 ? "s" : ""}. Check the figures below before running: this is a best-effort read.` });
    } catch (e) { setMsg({ tone: "watch", text: errorText(e) }); } finally { setExtracting(false); }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const segments: Record<string, Record<string, number>> = {};
    for (const r of rows) {
      if (!r.region.trim()) continue;
      const series: Record<string, number> = {};
      for (const p of periods) {
        const raw = (r.values[p] ?? "").replace(/,/g, "").trim();
        if (raw === "") continue;
        const n = Number(raw);
        if (Number.isNaN(n)) return setMsg({ tone: "watch", text: `${r.region || "A region"} (${p}): please enter numbers only.` });
        series[p] = n;
      }
      if (Object.keys(series).length) segments[r.region.trim()] = series;
    }
    if (Object.keys(segments).length === 0) return setMsg({ tone: "watch", text: "Enter revenue for at least one region." });
    setMsg(null);
    run.mutate({ segments });
  };

  const ccy = report.currency;
  return (
    <div className="space-y-4">
      <Card className="p-5 sm:p-6">
        <p className="text-sm text-ink-2">
          Regional revenue, share of total, growth and volatility are computed in Python from the figures you enter. The regional split comes from an annual report's
          segment note, which a statement export doesn't contain. For a region with a big swing the AI may suggest a <i>possible</i> reason from recent headlines, kept clearly apart from the facts.
        </p>

        <details className="mt-4 rounded-xl border border-line p-4">
          <summary className="cursor-pointer text-sm font-medium">Paste a segment note to pre-fill (optional)</summary>
          <div className="mt-3 space-y-3">
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={8000} aria-label="Segment note text"
              placeholder={"North America  1,200,000\nEurope  450,000\nIndia  168,000"}
              className="w-full rounded-xl border border-line-strong bg-black/30 p-3 text-sm placeholder:text-ink-3 focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/30" />
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-40"><Field label="Period" value={extractPeriod} onChange={(e) => setExtractPeriod(e.target.value)} placeholder="2024-FY" /></div>
              <Button type="button" variant="secondary" loading={extracting} disabled={!text.trim()} onClick={extract}><FileSearch className="size-4" aria-hidden /> Read regions</Button>
            </div>
          </div>
        </details>

        <form onSubmit={submit} noValidate className="mt-5 space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-40"><Field label="Add a period" value={periodDraft} onChange={(e) => setPeriodDraft(e.target.value)} placeholder="2024-FY"
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addPeriod(); } }} /></div>
            <Button type="button" variant="secondary" onClick={addPeriod}><Plus className="size-4" aria-hidden /> Add</Button>
            <div className="flex flex-wrap gap-1.5 pb-2">{periods.map((p) => (
              <button type="button" key={p} onClick={() => setPeriods(periods.filter((x) => x !== p))} title="Remove this period"
                className="rounded-full bg-white/10 px-2.5 py-1 text-xs text-ink-2 hover:bg-risk-bg hover:text-risk">{formatPeriod(p)} ×</button>
            ))}</div>
          </div>

          {periods.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[32rem] text-sm">
                <thead className="text-left text-xs text-ink-3"><tr><th className="pb-2 pr-3 font-medium">Region</th>{periods.map((p) => <th key={p} className="pb-2 pr-3 font-medium">{formatPeriod(p)}</th>)}<th /></tr></thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <td className="py-1 pr-3"><input aria-label={`Region ${i + 1} name`} value={r.region} maxLength={60} placeholder="e.g. India"
                        onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, region: e.target.value } : x)))}
                        className="h-10 w-full rounded-lg border border-line-strong bg-black/30 px-3 text-sm focus:border-brand-600 focus:outline-none" /></td>
                      {periods.map((p) => (
                        <td key={p} className="py-1 pr-3"><input aria-label={`${r.region || `Region ${i + 1}`} ${p}`} inputMode="decimal" value={r.values[p] ?? ""}
                          onChange={(e) => setCell(i, p, e.target.value)}
                          className="num h-10 w-full rounded-lg border border-line-strong bg-black/30 px-3 text-sm focus:border-brand-600 focus:outline-none" /></td>
                      ))}
                      <td className="py-1"><button type="button" aria-label="Remove region" onClick={() => setRows(rows.filter((_, j) => j !== i))} className="rounded p-2 text-ink-3 hover:text-risk"><Trash2 className="size-4" aria-hidden /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt-2 flex items-center gap-4">
                <Button type="button" variant="ghost" className="h-9" onClick={() => rows.length < 20 && setRows([...rows, { region: "", values: {} }])}><Plus className="size-4" aria-hidden /> Add region</Button>
                <span className="text-xs text-ink-3">Amounts in full {ccy ?? "currency"} units (the same unit as the statements).</span>
              </div>
            </div>
          )}
          {periods.length === 0 && <p className="text-sm text-ink-3">Add at least one period to start.</p>}
          {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
          {run.isError && <Alert tone="risk">{errorText(run.error)}</Alert>}
          <Button type="submit" loading={run.isPending} disabled={periods.length === 0}><Globe2 className="size-4" aria-hidden /> Analyse regions</Button>
        </form>
      </Card>
      {result?.status === "OK" && <GeographyResultView r={result} ccy={ccy} />}
      {result?.status === "UNAVAILABLE" && <Alert tone="watch">{result.reason}</Alert>}
    </div>
  );
}

function GeographyResultView({ r, ccy }: { r: GeographyResult; ccy: string | null }) {
  const regions = Object.entries(r.region_metrics);
  const latest = regions.map(([name, m]) => ({ name, share: m.revenue_share_pct.at(-1) ?? 0, growth: m.latest_yoy_growth_pct ?? 0 }));
  return (
    <>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-ink-3">
                <tr className="border-b border-line"><th className="px-4 py-3 font-medium">Region</th><th className="px-4 py-3 text-right font-medium">Latest revenue</th>
                  <th className="px-4 py-3 text-right font-medium">Share</th><th className="px-4 py-3 text-right font-medium">YoY</th><th className="px-4 py-3 text-right font-medium">Volatility</th><th className="px-4 py-3" /></tr>
              </thead>
              <tbody>
                {regions.map(([name, m]) => (
                  <tr key={name} className="border-b border-line/60 last:border-0">
                    <td className="px-4 py-3 font-medium">{name}<div className="text-[11px] font-normal text-ink-3">{formatPeriod(m.periods.at(-1))}</div></td>
                    <td className="num px-4 py-3 text-right">{formatMoney(m.revenue.at(-1), ccy)}</td>
                    <td className="num px-4 py-3 text-right">{m.revenue_share_pct.at(-1) == null ? "—" : `${m.revenue_share_pct.at(-1)!.toFixed(1)}%`}</td>
                    <td className={clsx("num px-4 py-3 text-right", (m.latest_yoy_growth_pct ?? 0) < 0 ? "text-risk" : "text-good")}>{m.latest_yoy_growth_pct == null ? "—" : `${m.latest_yoy_growth_pct > 0 ? "+" : ""}${m.latest_yoy_growth_pct.toFixed(1)}%`}</td>
                    <td className="num px-4 py-3 text-right text-ink-3">{m.volatility == null ? "—" : m.volatility.toFixed(1)}</td>
                    <td className="px-4 py-3">{m.notable_swing && <span className="rounded-full bg-watch-bg px-2 py-0.5 text-[11px] font-medium text-watch">Notable swing</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card className="p-5">
          <h3 className="text-sm font-semibold">Share of revenue and latest growth</h3>
          <div className="mt-3 h-56" role="img" aria-label="Each region's revenue share and latest growth">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={latest} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="name" {...axis} interval={0} />
                <YAxis width={40} {...axis} unit="%" />
                <Tooltip {...tooltip} cursor={{ fill: "#ffffff0a" }} formatter={(v, n) => [`${Number(v).toFixed(1)}%`, n]} />
                <Legend wrapperStyle={{ fontSize: 12, color: C.muted }} />
                <Bar dataKey="share" name="Share of revenue" fill={C.accentStrong} radius={[6, 6, 0, 0]} />
                <Bar dataKey="growth" name="YoY growth" fill={C.accent} radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {r.notable_regions.length > 0 && (
        <Card className="p-5">
          <h3 className="text-sm font-semibold">Headlines for notable swings</h3>
          <p className="text-xs text-ink-3">Context only: a headline is not proof of the cause.</p>
          <div className="mt-3 space-y-3">
            {r.notable_regions.map((region) => {
              const items = r.headlines[region] ?? [];
              return (
                <div key={region}>
                  <div className="flex items-center gap-2 text-sm font-medium">{region} <StatusBadge status={items.length ? "OK" : r.news_status[region]} /></div>
                  {items.length > 0
                    ? <ul className="mt-1 space-y-1 text-xs text-ink-2">{items.map((h, i) => <li key={i}>• {h.title} <span className="text-ink-3">({h.source}, {String(h.publishedAt).slice(0, 10)})</span></li>)}</ul>
                    : <p className="mt-1 text-xs text-ink-3">No headlines available{r.news_status[region] === "NOT_CONFIGURED" ? ": no news source is configured" : ""}, so no explanation is offered.</p>}
                </div>
              );
            })}
          </div>
        </Card>
      )}
      <NarrativeCard narrative={r.narrative} title="Fact and possible explanation" />
    </>
  );
}

/* ── Governance ─────────────────────────────────────────────────────────── */

interface Person { name: string; din: string }

export function GovernanceSection({ analysisId, report }: { analysisId: string; report: Report }) {
  const run = useAgent<GovernanceResult, { directors: Person[] }>(analysisId, "governance");
  const result = run.data ?? report.intelligence.governance;
  const [people, setPeople] = useState<Person[]>(() =>
    result?.findings?.length ? result.findings.map((f) => ({ name: f.name.startsWith("(") ? "" : f.name, din: f.din.startsWith("(") ? "" : f.din })) : [{ name: "", din: "" }]);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState<{ tone: "watch" | "info"; text: string } | null>(null);
  const [extracting, setExtracting] = useState(false);

  const extract = async () => {
    setExtracting(true); setMsg(null);
    try {
      const r = await api<{ directors: Person[] }>(`/analysis/${analysisId}/governance/extract`, { json: { text } });
      if (r.directors.length === 0) return setMsg({ tone: "info", text: "No director names or DINs were recognised. Enter them by hand below." });
      setPeople(r.directors);
      setMsg({ tone: "info", text: `Found ${r.directors.length} director${r.directors.length > 1 ? "s" : ""}. Check the names and DINs before running: this is a best-effort read.` });
    } catch (e) { setMsg({ tone: "watch", text: errorText(e) }); } finally { setExtracting(false); }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const directors = people.map((p) => ({ name: p.name.trim(), din: p.din.trim() })).filter((p) => p.name || p.din);
    if (directors.length === 0) return setMsg({ tone: "watch", text: "Enter at least one director's name or DIN." });
    if (directors.some((p) => p.din && !/^\d{8}$/.test(p.din))) return setMsg({ tone: "watch", text: "A DIN is exactly 8 digits." });
    setMsg(null);
    run.mutate({ directors });
  };

  return (
    <div className="space-y-4">
      <Alert tone="info">
        <b>A screen, not a verdict.</b> This looks for adverse keywords in recent headlines near each director's name. A match means <i>requires manual verification</i>, never proof of wrongdoing.
        Official registries (MCA, SEBI, IBBI) aren't connected, so statutory records are not checked. This is reported separately from the company's financial health and never affects the credit grade.
      </Alert>
      <Card className="p-5 sm:p-6">
        <details className="rounded-xl border border-line p-4">
          <summary className="cursor-pointer text-sm font-medium">Paste filing text to find directors (optional)</summary>
          <div className="mt-3 space-y-3">
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={20000} aria-label="Filing text"
              placeholder={"Jane Doe (DIN: 01234567)\nJohn Roe, DIN 07654321"}
              className="w-full rounded-xl border border-line-strong bg-black/30 p-3 text-sm placeholder:text-ink-3 focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/30" />
            <Button type="button" variant="secondary" loading={extracting} disabled={!text.trim()} onClick={extract}><FileSearch className="size-4" aria-hidden /> Find directors</Button>
          </div>
        </details>

        <form onSubmit={submit} noValidate className="mt-5 space-y-3">
          {people.map((p, i) => (
            <div key={i} className="flex flex-wrap items-end gap-3">
              <div className="min-w-[14rem] flex-1"><Field label={i === 0 ? "Director name" : ""} aria-label={`Director ${i + 1} name`} value={p.name} maxLength={80}
                onChange={(e) => setPeople(people.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} placeholder="Full name" /></div>
              <div className="w-44"><Field label={i === 0 ? "DIN (8 digits)" : ""} aria-label={`Director ${i + 1} DIN`} value={p.din} maxLength={8} inputMode="numeric"
                onChange={(e) => setPeople(people.map((x, j) => (j === i ? { ...x, din: e.target.value } : x)))} placeholder="Optional" /></div>
              <button type="button" aria-label="Remove director" onClick={() => setPeople(people.length > 1 ? people.filter((_, j) => j !== i) : [{ name: "", din: "" }])} className="mb-1 rounded p-2 text-ink-3 hover:text-risk"><Trash2 className="size-4" aria-hidden /></button>
            </div>
          ))}
          <Button type="button" variant="ghost" className="h-9" onClick={() => people.length < 12 && setPeople([...people, { name: "", din: "" }])}><Plus className="size-4" aria-hidden /> Add director</Button>
          {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
          {run.isError && <Alert tone="risk">{errorText(run.error)}</Alert>}
          <div><Button type="submit" loading={run.isPending}><ShieldQuestion className="size-4" aria-hidden /> Run governance screen</Button></div>
        </form>
      </Card>
      {result?.status === "UNAVAILABLE" && <Alert tone="watch">{result.reason}</Alert>}
      {result?.status === "OK" && <GovernanceResultView r={result} />}
    </div>
  );
}

function GovernanceResultView({ r }: { r: GovernanceResult }) {
  return (
    <>
      <div className="grid gap-3 lg:grid-cols-2">
        {r.findings?.map((f, i) => (
          <Card key={`${f.name}-${i}`} className="p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <span className="grid size-9 place-items-center rounded-full bg-white/10"><UserRound className="size-4 text-ink-2" aria-hidden /></span>
                <div><div className="font-medium">{f.name}</div><div className="num text-xs text-ink-3">DIN {f.din}</div></div>
              </div>
              <StatusBadge status={f.status === "WARN" ? "WARN" : f.status === "PASS" ? "PASS" : "UNAVAILABLE"} />
            </div>
            <dl className="mt-4 space-y-2 text-sm">
              <div className="flex items-center justify-between gap-3"><dt className="text-ink-3">Statutory registry (MCA / SEBI / IBBI)</dt><dd><StatusBadge status={f.statutory_lookup.status} /></dd></div>
              <div className="flex items-center justify-between gap-3"><dt className="text-ink-3">News source</dt><dd><StatusBadge status={f.news_status === "OK" ? "OK" : f.news_status} /></dd></div>
              <div className="flex items-center justify-between gap-3"><dt className="text-ink-3">Headlines scanned</dt><dd className="num">{f.adverse_mention_screen.articles_scanned}</dd></div>
            </dl>
            {f.adverse_mention_screen.matches.length > 0 && (
              <div className="mt-4 rounded-xl bg-watch-bg p-3">
                <div className="text-xs font-medium text-watch">Requires manual verification</div>
                <ul className="mt-1.5 space-y-1.5 text-xs text-ink-2">
                  {f.adverse_mention_screen.matches.map((m, j) => <li key={j}>• {m.title} <span className="text-ink-3">[{m.matched_keywords.join(", ")}]</span></li>)}
                </ul>
              </div>
            )}
            {f.statutory_lookup.status === "NOT_CONFIGURED" && <p className="mt-3 text-[11px] text-ink-3">{f.statutory_lookup.reason}</p>}
          </Card>
        ))}
      </div>
      <NarrativeCard narrative={r.narrative} title="Governance summary" />
    </>
  );
}
