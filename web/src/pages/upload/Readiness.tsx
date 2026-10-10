import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useStartAnalysis } from "@/lib/analysis";
import { CircleCheck, CircleDashed, Download, PenLine, Play } from "lucide-react";
import clsx from "clsx";
import { Alert, Button, Card } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { formatPeriod } from "@/lib/format";
import type { Workspace, WorkspaceLoaded } from "@/lib/types";
import { useWorkspaceMutation } from "@/lib/workspace";

export function Readiness({ ws }: { ws: WorkspaceLoaded }) {
  const [fixing, setFixing] = useState(false);
  const { readiness } = ws;
  return (
    <div className="space-y-4">
      <ul className="flex flex-wrap gap-2" aria-label="Agent readiness">
        {readiness.agents.map((a) => (
          <li key={a.key} className={clsx("inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium",
            a.ready ? "border-good/30 bg-good-bg text-good" : "border-line-strong text-ink-3")}>
            {a.ready ? <CircleCheck className="size-3.5" aria-hidden /> : <CircleDashed className="size-3.5" aria-hidden />}
            {a.label}<span className="sr-only">{a.ready ? " ready" : " missing data"}</span>
          </li>
        ))}
      </ul>

      {readiness.complete ? (
        <Alert tone="good"><b>All required data is present.</b> Every agent can run the full analysis.</Alert>
      ) : (
        <Alert tone="watch">
          <b>Incomplete data.</b> Missing: <span className="num">{readiness.missing_fields.join(", ")}</span>.
          {" "}These agents will be skipped unless you fill the gaps: {readiness.skipped_agents.join(", ")}.
          <div className="mt-3">
            <Button variant="secondary" className="h-9" onClick={() => setFixing((f) => !f)} aria-expanded={fixing}>
              <PenLine className="size-4" aria-hidden /> {fixing ? "Hide" : "Fix missing data"}
            </Button>
          </div>
        </Alert>
      )}

      {!readiness.complete && fixing && <SupplementGrid ws={ws} onApplied={() => setFixing(false)} />}

      <RunBar complete={readiness.complete} />
    </div>
  );
}

/** Starts the analysis and hands over to the Analysis page, which shows live progress. */
function RunBar({ complete }: { complete: boolean }) {
  const start = useStartAnalysis();
  const navigate = useNavigate();
  return (
    <Card className="space-y-3 p-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-sm font-medium">{complete ? "Run the full analysis" : "Run with the available data"}</div>
          <div className="text-xs text-ink-3">
            Credit grade, trends, peer benchmarks and the credit memo.{!complete && " Agents missing data will be skipped."}
          </div>
        </div>
        <Button loading={start.isPending} onClick={() => start.mutate(undefined, { onSuccess: () => navigate("/analysis") })}>
          <Play className="size-4" aria-hidden /> {complete ? "Run full analysis" : "Proceed anyway"}
        </Button>
      </div>
      {start.isError && <Alert tone="risk">{start.error instanceof ApiError ? start.error.message : "Couldn't start the analysis."}</Alert>}
    </Card>
  );
}

/* ── Missing-data grid ──────────────────────────────────────────────────── */

type Cells = Record<string, string>;
const cellKey = (field: string, period: string) => `${field}|${period}`;

function SupplementGrid({ ws, onApplied }: { ws: WorkspaceLoaded; onApplied: () => void }) {
  const { missing_fields: fields } = ws.readiness;
  const [cells, setCells] = useState<Cells>({});
  const [note, setNote] = useState<{ tone: "good" | "risk" | "watch"; text: string } | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const apply = useWorkspaceMutation((values: Record<string, Record<string, string>>) =>
    api<Workspace>("/workspace/supplement/apply", { json: { values } }));

  const autofetch = async (provider: "fmp" | "alphavantage") => {
    setNote(null);
    try {
      const r = await api<{ resolved_fields: string[]; values: Record<string, Record<string, number>>; errors: string[] }>(
        "/workspace/supplement/autofetch", { json: { provider } });
      const next = { ...cells };
      for (const [field, per] of Object.entries(r.values)) for (const [period, v] of Object.entries(per)) next[cellKey(field, period)] = String(Math.round(v));
      setCells(next);
      const name = provider === "fmp" ? "FMP" : "Alpha Vantage";
      setNote(r.resolved_fields.length
        ? { tone: "good", text: `${name} found: ${r.resolved_fields.join(", ")}. Review the values below, then apply.` }
        : { tone: "risk", text: `${name} couldn't find any of the missing fields. Enter them manually below.` });
    } catch (e) {
      setNote({ tone: "risk", text: e instanceof ApiError ? e.message : "Auto-fetch failed." });
    }
  };

  const submit = () => {
    setErrors({});
    const values: Record<string, Record<string, string>> = {};
    for (const f of fields) {
      values[f] = {};
      for (const p of ws.periods) values[f][p] = cells[cellKey(f, p)] ?? "";
    }
    apply.mutate(values, {
      onSuccess: onApplied,
      onError: (e) => {
        if (e instanceof ApiError) setErrors(e.fields);
      },
    });
  };

  const providers = [
    { key: "fmp" as const, label: "Fetch via FMP", on: ws.supplement.fmp },
    { key: "alphavantage" as const, label: "Fetch via Alpha Vantage", on: ws.supplement.alphavantage },
  ];

  return (
    <Card className="space-y-5 p-5 sm:p-6">
      {ws.supplement.ticker && (
        <section aria-label="Auto-fetch">
          <h3 className="text-sm font-semibold">Step 1 — Auto-fetch</h3>
          <div className="mt-3 flex flex-wrap gap-3">
            {providers.map((p) => (
              <Button key={p.key} variant="secondary" className="h-9" disabled={!p.on} onClick={() => autofetch(p.key)}
                title={p.on ? undefined : "This provider isn't configured on the server."}><Download className="size-4" aria-hidden /> {p.label}</Button>
            ))}
          </div>
          {!providers.some((p) => p.on) && <p className="mt-2 text-xs text-ink-3">No data provider keys are configured on the server, so enter the values manually.</p>}
          {note && <div className="mt-3"><Alert tone={note.tone}>{note.text}</Alert></div>}
        </section>
      )}

      <section aria-label="Enter values">
        <h3 className="text-sm font-semibold">{ws.supplement.ticker ? "Step 2 — Review or enter values" : "Enter the missing values"}</h3>
        <p className="mt-1 text-xs text-ink-3">Use the same unit as your other figures. Leave a cell blank to skip it.</p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[28rem] text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-3">
                <th className="py-2 pr-3 font-medium">Period</th>
                {fields.map((f) => <th key={f} className="px-1.5 py-2 font-medium num">{f}</th>)}
              </tr>
            </thead>
            <tbody>
              {ws.periods.map((p) => (
                <tr key={p} className="border-t border-line/60">
                  <th scope="row" className="py-1.5 pr-3 text-left font-medium text-ink-2">{formatPeriod(p)}</th>
                  {fields.map((f) => {
                    const k = cellKey(f, p);
                    return (
                      <td key={f} className="px-1.5 py-1.5">
                        <input
                          inputMode="decimal" placeholder="e.g. 150000" value={cells[k] ?? ""} aria-label={`${f} for ${formatPeriod(p)}`}
                          aria-invalid={!!errors[k]} title={errors[k]}
                          onChange={(e) => setCells({ ...cells, [k]: e.target.value })}
                          className={clsx("num h-9 w-full min-w-[7rem] rounded-lg border bg-black/30 px-2.5 text-sm placeholder:text-ink-3 focus:border-brand-600 focus:outline-none",
                            errors[k] ? "border-risk" : "border-line-strong")}
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {Object.keys(errors).length > 0 && (
          <div className="mt-3"><Alert tone="risk">
            <ul className="list-disc pl-4">{Object.entries(errors).map(([k, m]) => <li key={k}><span className="num">{k.replace("|", " / ")}</span>: {m}</li>)}</ul>
          </Alert></div>
        )}
        {apply.isError && Object.keys(errors).length === 0 && <div className="mt-3"><Alert tone="risk">{apply.error instanceof ApiError ? apply.error.message : "Could not apply the values."}</Alert></div>}
      </section>

      <Button onClick={submit} loading={apply.isPending}>Apply supplemental data</Button>
    </Card>
  );
}
