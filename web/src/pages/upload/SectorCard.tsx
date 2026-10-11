import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Field, SelectField } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { WorkspaceLoaded } from "@/lib/types";
import { WORKSPACE_KEY } from "@/lib/workspace";

interface SectorInfo { sectors: string[]; input_fields: Record<string, string[]> }

const LABELS: Record<string, string> = {
  general: "General (no sector-specific metrics)", saas: "SaaS / software", banking: "Banking / NBFC",
  retail: "Retail / e-commerce", manufacturing: "Manufacturing",
};

/** "churn_rate_pct" -> "Churn rate (%)"; "gross_npa" -> "Gross npa" */
function humanise(key: string): string {
  const pct = key.endsWith("_pct");
  const words = key.replace(/_pct$/, "").replace(/_/g, " ");
  return `${words.charAt(0).toUpperCase()}${words.slice(1)}${pct ? " (%)" : ""}`;
}

export function SectorCard({ ws }: { ws: WorkspaceLoaded }) {
  const qc = useQueryClient();
  const info = useQuery({ queryKey: ["sectors"], queryFn: () => api<SectorInfo>("/sectors"), staleTime: Infinity });
  const [sector, setSector] = useState(ws.sector || "general");
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(ws.domain_inputs ?? {}).map(([k, v]) => [k, String(v)])));
  const [local, setLocal] = useState("");
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: (body: { sector: string; domain_inputs: Record<string, number> }) => api("/workspace/sector", { method: "PUT", json: body }),
    onSuccess: () => { setSaved(true); qc.invalidateQueries({ queryKey: WORKSPACE_KEY }); },
  });

  const fields = info.data?.input_fields[sector] ?? [];
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSaved(false);
    const domain_inputs: Record<string, number> = {};
    for (const k of fields) {
      const raw = (values[k] ?? "").replace(/,/g, "").trim();
      if (raw === "") continue;
      const n = Number(raw);
      if (Number.isNaN(n)) return setLocal(`${humanise(k)}: please enter a number.`);
      domain_inputs[k] = n;
    }
    setLocal("");
    save.mutate({ sector, domain_inputs });
  };

  return (
    <Card className="p-5 sm:p-6">
      <form onSubmit={submit} noValidate className="space-y-5">
        <div className="max-w-sm">
          <SelectField label="Industry" value={sector} onChange={(e) => { setSector(e.target.value); setSaved(false); }} disabled={info.isPending}>
            {(info.data?.sectors ?? ["general"]).map((s) => <option key={s} value={s}>{LABELS[s] ?? s}</option>)}
          </SelectField>
        </div>

        {sector === "general" ? (
          <p className="text-sm text-ink-3">No industry-specific metrics. Pick an industry to add the measures investors look for in it. Where an input isn't supplied, the metric is marked as needing it rather than guessed.</p>
        ) : (
          <>
            <p className="text-sm text-ink-2">
              Optional operational figures that no financial statement carries. Fill in what you have; anything left blank shows as "Needs document" in the analysis.
              Enter amounts in full {ws.entity.currency ?? "currency"} units, and percentages as plain numbers (e.g. 3.5 for 3.5%).
            </p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {fields.map((k) => (
                <Field key={k} label={humanise(k)} inputMode="decimal" value={values[k] ?? ""}
                  onChange={(e) => { setValues({ ...values, [k]: e.target.value }); setSaved(false); }} />
              ))}
            </div>
          </>
        )}

        {local && <Alert tone="watch">{local}</Alert>}
        {save.isError && <Alert tone="risk">{save.error instanceof ApiError ? save.error.message : "Couldn't save. Please try again."}</Alert>}
        {saved && <Alert tone="good">Saved. This applies the next time you run the analysis, so run it again if one already exists.</Alert>}
        <Button type="submit" variant="secondary" loading={save.isPending}>Save industry settings</Button>
      </form>
    </Card>
  );
}
