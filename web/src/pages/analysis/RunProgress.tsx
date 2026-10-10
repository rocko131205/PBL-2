import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui";
import type { Stage } from "@/lib/analysis";

export function RunProgress({ stages, entity }: { stages: Stage[]; entity: string }) {
  const done = stages.filter((s) => s.status === "done").length;
  const pct = Math.round((done / Math.max(stages.length, 1)) * 100);
  return (
    <Card className="p-6 sm:p-8">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="text-xs uppercase tracking-wide text-ink-3">Analysing</div>
          <div className="text-lg font-semibold">{entity}</div>
        </div>
        <div className="num text-sm text-ink-2" aria-live="polite">{done} of {stages.length} stages · {pct}%</div>
      </div>
      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/10" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="accent-gradient h-full rounded-full transition-all duration-500" style={{ width: `${Math.max(pct, 4)}%` }} />
      </div>
      <ol className="mt-6 space-y-3">
        {stages.map((s) => (
          <li key={s.key} className="flex items-center gap-3 text-sm">
            {s.status === "done" ? <CheckCircle2 className="size-5 text-good" aria-hidden />
              : s.status === "running" ? <Loader2 className="size-5 animate-spin text-brand-700" aria-hidden />
                : <Circle className="size-5 text-ink-3" aria-hidden />}
            <span className={clsx(s.status === "pending" ? "text-ink-3" : "text-ink", s.status === "running" && "font-medium")}>{s.label}</span>
            <span className="sr-only">— {s.status}</span>
          </li>
        ))}
      </ol>
      <p className="mt-6 text-xs text-ink-3">
        Metrics are computed deterministically; the AI stages only add narrative. This usually takes under a minute — you can leave this page and come back.
      </p>
    </Card>
  );
}
