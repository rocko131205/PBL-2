import { useState, type FormEvent } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Calculator } from "lucide-react";
import clsx from "clsx";
import { Alert, Button, Card, Field, SelectField } from "@/components/ui";
import { C, axis, tooltip } from "@/components/chart";
import { ApiError } from "@/lib/api";
import { useDscr, type DscrTerms, type DscrView, type Report } from "@/lib/analysis";
import { formatRatio } from "@/lib/format";

const STRUCTURES = [["equal_installment", "Equal instalments"], ["bullet", "Bullet (repay at maturity)"], ["balloon", "Balloon"]];
const RISK_TONE: Record<string, string> = { LOW: "text-good", MODERATE: "text-watch", HIGH: "text-risk", CRITICAL: "text-risk" };

export function DscrSection({ analysisId, report }: { analysisId: string; report: Report }) {
  if (!report.has_record) return null;
  if (report.dscr_bases.length === 0) {
    return <Alert tone="watch">No cash-flow basis is available for DSCR (it needs EBITDA, operating income or operating cash flow). A listed ticker usually includes the cash-flow statement.</Alert>;
  }
  return (
    <div className="space-y-4">
      <DscrForm analysisId={analysisId} report={report} />
      {report.dscr && <DscrResult view={report.dscr} currency={report.currency} />}
    </div>
  );
}

function DscrForm({ analysisId, report }: { analysisId: string; report: Report }) {
  const prev = report.dscr_terms;
  const [f, setF] = useState({
    principal: prev ? String(prev.principal) : "",
    annual_rate_pct: String(prev?.annual_rate_pct ?? 10),
    tenure_years: String(prev?.tenure_years ?? 5),
    structure: prev?.structure ?? "equal_installment",
    moratorium_years: String(prev?.moratorium_years ?? 0),
    existing_annual_debt_service: String(prev?.existing_annual_debt_service ?? 0),
    basis: prev?.basis ?? report.dscr_bases[0].key,
  });
  const [local, setLocal] = useState("");
  const run = useDscr(analysisId);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const ccy = report.currency ?? "currency";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const num = (s: string) => Number(s.replace(/,/g, ""));
    const terms: DscrTerms = {
      principal: num(f.principal), annual_rate_pct: num(f.annual_rate_pct), tenure_years: Math.round(num(f.tenure_years)),
      structure: f.structure, moratorium_years: Math.round(num(f.moratorium_years)),
      existing_annual_debt_service: num(f.existing_annual_debt_service || "0"), basis: f.basis,
    };
    if (!(terms.principal > 0)) return setLocal("Enter a loan amount greater than zero.");
    if (terms.tenure_years < 1 || terms.tenure_years > 40) return setLocal("Tenure must be between 1 and 40 years.");
    if (terms.moratorium_years >= terms.tenure_years) return setLocal("The moratorium must be shorter than the tenure.");
    if (Object.values(terms).some((v) => typeof v === "number" && Number.isNaN(v))) return setLocal("Please enter numbers only.");
    setLocal("");
    run.mutate(terms);
  };

  return (
    <Card className="p-5 sm:p-6">
      <p className="text-sm text-ink-2">
        Enter the proposed loan. We build the year-by-year repayment schedule, compute the DSCR for every year and report the
        <b className="text-ink"> minimum</b> — the tightest year, which is what a lender underwrites against — plus how it holds up under stress.
      </p>
      <form onSubmit={submit} noValidate className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field label={`Loan amount (${ccy})`} inputMode="decimal" value={f.principal} onChange={set("principal")} placeholder="e.g. 50000000" required />
        <Field label="Interest rate (% a year)" inputMode="decimal" value={f.annual_rate_pct} onChange={set("annual_rate_pct")} />
        <Field label="Tenure (years)" inputMode="numeric" value={f.tenure_years} onChange={set("tenure_years")} />
        <SelectField label="Repayment structure" value={f.structure} onChange={set("structure")}>
          {STRUCTURES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </SelectField>
        <Field label="Moratorium (interest-only years)" inputMode="numeric" value={f.moratorium_years} onChange={set("moratorium_years")} />
        <Field label={`Existing annual debt service (${ccy})`} inputMode="decimal" value={f.existing_annual_debt_service} onChange={set("existing_annual_debt_service")} />
        <div className="sm:col-span-2 lg:col-span-3">
          <SelectField label="Cash available for debt service (numerator)" value={f.basis} onChange={set("basis")}>
            {report.dscr_bases.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
          </SelectField>
        </div>
        <div className="sm:col-span-2 lg:col-span-3 space-y-3">
          {local && <Alert tone="watch">{local}</Alert>}
          {run.isError && <Alert tone="risk">{run.error instanceof ApiError ? run.error.message : "Couldn't compute DSCR."}</Alert>}
          <Button type="submit" loading={run.isPending}><Calculator className="size-4" aria-hidden /> Compute debt serviceability</Button>
        </div>
      </form>
    </Card>
  );
}

function DscrResult({ view, currency }: { view: DscrView; currency: string | null }) {
  if (view.min_dscr == null) {
    return <Alert tone="watch">DSCR couldn't be computed with the available data. {view.notes.join(" ")}</Alert>;
  }
  const chart = view.schedule.map((r) => ({ year: `Y${r.year}`, dscr: r.dscr }));
  const tone = view.min_dscr >= 1.5 ? "text-good" : view.min_dscr >= 1 ? "text-watch" : "text-risk";
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Minimum DSCR" value={<span className={tone}>{formatRatio(view.min_dscr)}</span>} hint={`tightest: year ${view.min_dscr_year}`} />
        <Kpi label="Average DSCR" value={formatRatio(view.avg_dscr)} hint={`over ${view.tenure_years} years`} />
        <Kpi label="Risk level" value={<span className={RISK_TONE[view.risk_level] ?? ""}>{view.risk_level}</span>} />
        <Kpi label="Cash basis" value={view.numerator_basis.toUpperCase()} hint={`${view.numerator_display} a year`} />
      </div>
      {view.verdict && <Alert tone={view.verdict.tone}>{view.verdict.text}</Alert>}
      {(view.interest_coverage != null || view.debt_to_ebitda != null) && (
        <p className="text-sm text-ink-2">
          Companion coverage —{view.interest_coverage != null && <> interest coverage <b className="num text-ink">{formatRatio(view.interest_coverage)}</b></>}
          {view.interest_coverage != null && view.debt_to_ebitda != null && " ·"}
          {view.debt_to_ebitda != null && <> debt / EBITDA <b className="num text-ink">{formatRatio(view.debt_to_ebitda)}</b></>}
        </p>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="p-5 sm:p-6">
          <h3 className="text-sm font-semibold">DSCR by year</h3>
          <div className="mt-4 h-64" role="img" aria-label="DSCR by year with the 1.0x danger line">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chart} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="year" {...axis} />
                <YAxis width={44} {...axis} tickFormatter={(v: number) => `${v}x`} domain={[0, (max: number) => Math.max(2, Math.ceil(max * 1.15))]} />
                <Tooltip {...tooltip} formatter={(v) => [formatRatio(Number(v)), "DSCR"]} />
                <ReferenceLine y={1} stroke={C.risk} strokeDasharray="5 5" label={{ value: "1.0x", position: "insideTopRight", fill: C.risk, fontSize: 11 }} />
                <Line dataKey="dscr" type="monotone" stroke={C.accent} strokeWidth={2.4} dot={{ r: 4, fill: C.accent }} isAnimationActive={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-ink-3">Below the 1.0× line, that year's cash can't cover its debt service.</p>
        </Card>

        <Card className="overflow-hidden">
          <h3 className="px-5 pt-5 text-sm font-semibold sm:px-6">Amortisation schedule</h3>
          <div className="mt-3 max-h-80 overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-solid text-left text-xs text-ink-3">
                <tr><th className="px-5 py-2.5 font-medium">Year</th><th className="px-3 py-2.5 text-right font-medium">Principal</th><th className="px-3 py-2.5 text-right font-medium">Interest</th><th className="px-3 py-2.5 text-right font-medium">Payment</th><th className="px-5 py-2.5 text-right font-medium">DSCR</th></tr>
              </thead>
              <tbody>
                {view.schedule.map((r) => (
                  <tr key={r.year} className="border-t border-line/60">
                    <td className="px-5 py-2">Y{r.year}</td>
                    <td className="num px-3 py-2 text-right">{r.principal_display}</td>
                    <td className="num px-3 py-2 text-right">{r.interest_display}</td>
                    <td className="num px-3 py-2 text-right">{r.total_payment_display}</td>
                    <td className={clsx("num px-5 py-2 text-right", r.dscr != null && r.dscr < 1 ? "text-risk" : "")}>{formatRatio(r.dscr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {view.stress_results.length > 0 && (
        <Card className="overflow-hidden">
          <h3 className="px-5 pt-5 text-sm font-semibold sm:px-6">Stress tests — how the minimum DSCR holds up if things go wrong</h3>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-ink-3"><tr className="border-b border-line">
                <th className="px-5 py-2.5 font-medium">Scenario</th><th className="px-3 py-2.5 text-right font-medium">Min DSCR</th><th className="px-3 py-2.5 text-right font-medium">vs base</th><th className="px-5 py-2.5 text-right font-medium">Below 1.0×?</th>
              </tr></thead>
              <tbody>
                {view.stress_results.map((s) => (
                  <tr key={s.scenario} className={clsx("border-b border-line/60 last:border-0", s.breaches_1x && "bg-risk-bg")}>
                    <td className="px-5 py-2.5">{s.description}</td>
                    <td className="num px-3 py-2.5 text-right">{formatRatio(s.min_dscr)}</td>
                    <td className="num px-3 py-2.5 text-right text-ink-3">{s.delta_vs_base == null ? "—" : `${s.delta_vs_base >= 0 ? "+" : ""}${s.delta_vs_base.toFixed(2)}`}</td>
                    <td className={clsx("px-5 py-2.5 text-right font-medium", s.breaches_1x ? "text-risk" : "text-ink-3")}>{s.breaches_1x ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {view.breaches > 0 && <div className="p-5 pt-3"><Alert tone="risk">Coverage falls below 1.0× in {view.breaches} stress scenario{view.breaches > 1 ? "s" : ""} — the borrower would struggle to repay if these occur.</Alert></div>}
        </Card>
      )}

      <details className="glass rounded-2xl p-5">
        <summary className="cursor-pointer text-sm font-medium">DSCR methodology & assumptions</summary>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-ink-2">
          {view.method.map((m) => <li key={m}>{m}</li>)}
          {view.notes.map((n) => <li key={n} className="text-watch">{n}</li>)}
        </ul>
      </details>
      <span className="sr-only">Amounts in {currency ?? "the statement currency"}.</span>
    </div>
  );
}

function Kpi({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <Card className="p-5">
      <div className="text-xs text-ink-3">{label}</div>
      <div className="num mt-1.5 text-2xl font-semibold">{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-3">{hint}</div>}
    </Card>
  );
}
