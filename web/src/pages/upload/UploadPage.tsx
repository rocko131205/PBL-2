import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, Trash2 } from "lucide-react";
import clsx from "clsx";
import { Alert, Button, Card, SelectField, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Workspace, WorkspaceLoaded } from "@/lib/types";
import { useClearWorkspace, useCredibility, useWorkspace, useWorkspaceMutation } from "@/lib/workspace";
import { CredibilityCard } from "./CredibilityCard";
import { KpiCards } from "./KpiCards";
import { Readiness } from "./Readiness";
import { SourcePicker } from "./SourcePicker";

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        {subtitle && <p className="text-sm text-ink-3">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

export default function UploadPage() {
  const { data: ws, isLoading, error } = useWorkspace();
  if (isLoading) return <Spinner label="Loading your workspace" />;
  if (error || !ws) return <Alert tone="risk">{error instanceof ApiError ? error.message : "Couldn't load your workspace."}</Alert>;

  return (
    <div className="space-y-10 pb-10">
      <Section title="Financial data ingestion" subtitle="Choose a source: Bloomberg PDF, listed ticker, or private company CSV.">
        <SourcePicker active={ws.loaded ? ws.source : null} />
      </Section>
      {ws.loaded && <Loaded key={ws.source_label} ws={ws} />}
    </div>
  );
}

function Loaded({ ws }: { ws: WorkspaceLoaded }) {
  const credibility = useCredibility(true);
  return (
    <>
      <DatasetBar ws={ws} />
      <Section title="Extracted key metrics" subtitle={`Source: ${ws.source_label}`}>
        {ws.scale.applicable && <ScaleSelect ws={ws} />}
        <KpiCards cards={ws.cards} />
      </Section>

      <Section title="Data credibility" subtitle="Automated checks on source authenticity, consistency and completeness">
        <CredibilityCard data={credibility.data} loading={credibility.isPending} error={credibility.error} />
      </Section>

      <Section title="Qualitative context" subtitle="Optional management commentary or earnings-call notes. It adds soft context to the analysis and never changes a computed number.">
        <Qualitative initial={ws.qualitative} />
      </Section>

      <Preview rows={ws.preview} />

      <Section title="Readiness" subtitle="Which agents have the data they need">
        <Readiness ws={ws} />
      </Section>
    </>
  );
}

function DatasetBar({ ws }: { ws: WorkspaceLoaded }) {
  const clear = useClearWorkspace();
  return (
    <Card className="flex flex-wrap items-center justify-between gap-3 p-4 sm:px-6">
      <div>
        <div className="text-xs uppercase tracking-wide text-ink-3">Active dataset</div>
        <div className="mt-0.5 font-semibold">{ws.entity.name}</div>
        <div className="text-xs text-ink-3">{ws.source_label} · {ws.fields_loaded.length} fields{ws.entity.currency ? ` · ${ws.entity.currency}` : ""}</div>
      </div>
      <Button variant="ghost" loading={clear.isPending} onClick={() => clear.mutate()}><Trash2 className="size-4" aria-hidden /> Clear data</Button>
    </Card>
  );
}

function ScaleSelect({ ws }: { ws: WorkspaceLoaded }) {
  const set = useWorkspaceMutation((multiplier: number) => api<Workspace>("/workspace/scale", { method: "PUT", json: { multiplier } }));
  const { multiplier, options } = ws.scale;
  return (
    <div className="max-w-sm space-y-2">
      <SelectField label="Figures in the source are reported in" value={String(multiplier)}
        onChange={(e) => set.mutate(Number(e.target.value))} disabled={set.isPending}>
        {options.map((o) => <option key={o.key} value={o.multiplier}>{o.label}</option>)}
      </SelectField>
      <p className="text-xs text-ink-3">
        If the statement says “₹ in millions” or “in crore”, pick that unit so the numbers show their true size.
        {multiplier !== 1 && <> Showing values ×{multiplier.toLocaleString("en-US")}.</>}
      </p>
      {set.isError && <Alert tone="risk">{set.error instanceof ApiError ? set.error.message : "Could not change the scale."}</Alert>}
    </div>
  );
}

/** Notes autosave shortly after you stop typing. */
function Qualitative({ initial }: { initial: string }) {
  const [text, setText] = useState(initial);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const saved = useRef(initial);

  useEffect(() => {
    if (text === saved.current) return;
    setState("saving");
    const t = setTimeout(() => {
      api("/workspace/qualitative", { method: "PUT", json: { text } })
        .then(() => { saved.current = text; setState("saved"); })
        .catch(() => setState("error"));
    }, 800);
    return () => clearTimeout(t);
  }, [text]);

  return (
    <div>
      <textarea
        value={text} onChange={(e) => setText(e.target.value)} rows={5} maxLength={20000} aria-label="Qualitative context"
        placeholder="e.g. Management guided to 20% revenue growth next year and flagged supply-chain risk in Q3…"
        className="w-full rounded-2xl border border-line-strong bg-black/30 p-4 text-sm placeholder:text-ink-3 focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/30"
      />
      <div className="mt-1 h-4 text-xs text-ink-3" role="status">
        {state === "saving" && "Saving…"}{state === "saved" && "Saved"}{state === "error" && <span className="text-risk">Couldn't save. Your text is still here.</span>}
      </div>
    </div>
  );
}

function Preview({ rows }: { rows: WorkspaceLoaded["preview"] }) {
  const [open, setOpen] = useState(false);
  if (rows.length === 0) return null;
  return (
    <div>
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline">
        <ChevronDown className={clsx("size-4 transition", open && "rotate-180")} aria-hidden /> Raw data preview
      </button>
      {open && (
        <Card className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line text-left text-xs text-ink-3"><th className="px-4 py-2.5 font-medium">Field</th><th className="px-4 py-2.5 font-medium">Period</th><th className="px-4 py-2.5 text-right font-medium">Value (as loaded)</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.field + r.period} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-2 num">{r.field}</td><td className="px-4 py-2">{r.period}</td>
                  <td className="num px-4 py-2 text-right">{r.value.toLocaleString("en-US")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
