import { Sparkles } from "lucide-react";
import clsx from "clsx";
import { Alert, Card } from "@/components/ui";
import type { Narrative } from "@/lib/analysis";

/**
 * How trustworthy a figure is, at a glance. A computed figure shows no badge; an estimate or a gap must
 * never be mistaken for a confirmed number, so every other state is labelled.
 */
const BADGES: Record<string, { label: string; cls: string; title: string }> = {
  ESTIMATED: { label: "Estimate", cls: "bg-watch-bg text-watch", title: "Computed using a disclosed simplifying assumption. Not a confirmed figure." },
  INSUFFICIENT_DATA: { label: "No data", cls: "bg-white/10 text-ink-3", title: "Not enough ingested data to compute this." },
  NOT_APPLICABLE: { label: "n/a", cls: "bg-white/10 text-ink-3", title: "Doesn't apply to this company." },
  REQUIRES_ADDITIONAL_DOCUMENT: { label: "Needs document", cls: "bg-info-bg text-info", title: "Needs a document or operational input that isn't in the financial statements." },
  REQUIRES_EXTERNAL_DATA: { label: "Needs external data", cls: "bg-info-bg text-info", title: "Needs a data source that isn't configured." },
  NOT_CONFIGURED: { label: "Not configured", cls: "bg-white/10 text-ink-3", title: "No data source is configured for this check." },
  UNAVAILABLE: { label: "Unavailable", cls: "bg-white/10 text-ink-3", title: "Couldn't be retrieved." },
  ERROR: { label: "Error", cls: "bg-risk-bg text-risk", title: "The source returned an error." },
  PASS: { label: "Pass", cls: "bg-good-bg text-good", title: "" },
  WARN: { label: "Watch", cls: "bg-watch-bg text-watch", title: "" },
  FAIL: { label: "Concern", cls: "bg-risk-bg text-risk", title: "" },
  SKIP: { label: "Skipped", cls: "bg-white/10 text-ink-3", title: "Not enough history to evaluate." },
  OK: { label: "OK", cls: "bg-good-bg text-good", title: "" },
};

export function StatusBadge({ status, className }: { status?: string | null; className?: string }) {
  if (!status || status === "VALID") return null;
  const b = BADGES[status] ?? { label: status.replace(/_/g, " ").toLowerCase(), cls: "bg-white/10 text-ink-3", title: "" };
  return (
    <span title={b.title || undefined} className={clsx("inline-flex w-fit shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium", b.cls, className)}>
      {b.label}
    </span>
  );
}

/** The AI's wording of a result the engines already decided. Says plainly when it isn't available. */
export function NarrativeCard({ narrative, title = "In plain English" }: { narrative?: Narrative | null; title?: string }) {
  if (!narrative) return null;
  if (!narrative.available) {
    return <Alert tone="info">{narrative.warnings[0] ?? "The AI narrative is unavailable right now."} Every figure above is complete without it.</Alert>;
  }
  return (
    <Card className="p-5 sm:p-6">
      <h3 className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="size-4 text-brand-700" aria-hidden /> {title}</h3>
      <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-ink-2">{narrative.text}</p>
      {narrative.warnings.length > 0 && <p className="mt-3 text-xs text-watch">⚠ {narrative.warnings.join(" ")}</p>}
      <p className="mt-3 text-xs text-ink-3">Written by the AI from the computed results above. It can't change any number.</p>
    </Card>
  );
}
