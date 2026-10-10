import { useState } from "react";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";
import { Alert, Card, Spinner } from "@/components/ui";
import { ApiError } from "@/lib/api";
import type { Credibility, CredibilityCheck } from "@/lib/types";

const CONFIDENCE = {
  HIGH: { label: "High confidence", stroke: "#34d399", pill: "bg-good-bg text-good" },
  MEDIUM: { label: "Medium confidence", stroke: "#fbbf24", pill: "bg-watch-bg text-watch" },
  LOW: { label: "Low confidence", stroke: "#fb7185", pill: "bg-risk-bg text-risk" },
} as const;

const STATUS: Record<CredibilityCheck["status"], { label: string; cls: string }> = {
  pass: { label: "Pass", cls: "bg-good-bg text-good" },
  warn: { label: "Warn", cls: "bg-watch-bg text-watch" },
  fail: { label: "Fail", cls: "bg-risk-bg text-risk" },
  skip: { label: "Skipped", cls: "bg-white/10 text-ink-3" },
};

const R = 32;
const C = 2 * Math.PI * R;

interface Props { data?: Credibility; loading: boolean; error: unknown }

export function CredibilityCard({ data, loading, error }: Props) {
  const [open, setOpen] = useState(false);
  if (loading) return <Card><Spinner label="Running credibility checks" /></Card>;
  if (error || !data) {
    return <Alert tone="risk">{error instanceof ApiError ? error.message : "Credibility checks are unavailable right now."}</Alert>;
  }
  const tone = CONFIDENCE[data.confidence];
  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-6">
        <svg viewBox="0 0 80 80" className="size-24 shrink-0 -rotate-90" role="img" aria-label={`Credibility score ${data.score} out of 100`}>
          <circle cx="40" cy="40" r={R} fill="none" stroke="#ffffff14" strokeWidth="8" />
          <circle cx="40" cy="40" r={R} fill="none" stroke={tone.stroke} strokeWidth="8" strokeLinecap="round"
            strokeDasharray={`${(data.score / 100) * C} ${C}`} />
        </svg>
        <div>
          <div className="text-xs uppercase tracking-wide text-ink-3">Data credibility</div>
          <div className="num text-4xl font-semibold">{data.score}<span className="text-lg text-ink-3"> / 100</span></div>
          <span className={clsx("mt-1 inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium", tone.pill)}>{tone.label}</span>
        </div>
        <p className="max-w-sm text-sm text-ink-2">
          Automated checks on source authenticity, internal consistency and completeness. The score is the weighted share of checks that passed (skipped checks are ignored).
        </p>
      </div>

      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline">
        <ChevronDown className={clsx("size-4 transition", open && "rotate-180")} aria-hidden /> {open ? "Hide" : "View"} the {data.checks.length} checks
      </button>
      {open && (
        <ul className="mt-3 divide-y divide-line">
          {data.checks.map((c) => (
            <li key={c.name} className="flex items-start gap-3 py-3">
              <span className={clsx("mt-0.5 w-16 shrink-0 rounded-full px-2 py-0.5 text-center text-[11px] font-medium", STATUS[c.status].cls)}>{STATUS[c.status].label}</span>
              <div>
                <div className="text-sm font-medium">{c.name}</div>
                <div className="text-xs text-ink-3">{c.detail}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
