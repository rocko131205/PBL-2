import { BarChart3, Droplets, Layers, Network, ShieldAlert, ShieldCheck } from "lucide-react";
import { Card } from "@/components/ui";

const MAPPING = [
  { Icon: BarChart3, agent: "Revenue agent", maps: "Income stability · earnings trend analysis" },
  { Icon: Droplets, agent: "Liquidity agent", maps: "Working-capital adequacy · LCR-adjacent indicators" },
  { Icon: Layers, agent: "Balance sheet agent", maps: "Leverage ratio monitoring · asset-quality signals" },
  { Icon: Network, agent: "Cross-reference agent", maps: "Integrated risk narrative · Pillar 2 reporting aid" },
];
const USES = [
  "Structured financial statement review workflows",
  "Preliminary credit background checks based on public filings",
  "Risk trend monitoring across multiple reporting periods",
  "Generation of explainable, auditable financial summaries",
];

export default function BaselPage() {
  return (
    <div className="space-y-6 pb-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Basel III alignment</h1>
        <p className="text-sm text-ink-3">How this system supports regulatory risk-governance frameworks.</p>
      </div>

      <Card className="p-6">
        <h2 className="text-sm font-semibold">System overview</h2>
        <p className="mt-2 max-w-4xl text-sm leading-relaxed text-ink-2">
          FinVeritas supports Basel III-aligned risk-governance workflows with transparent, auditable and explainable financial
          risk indicators derived from structured financial statements. Every numeric computation is performed deterministically in
          Python; the language model is used only to explain pre-computed metrics, which keeps the output fully auditable.
        </p>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-6">
          <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">Pillar 2</span>
          <h2 className="mt-3 font-semibold">Supervisory review</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-2">
            Structured, explainable outputs for internal credit-risk review. Revenue trends, liquidity ratios and balance-sheet
            leverage are presented transparently, so risk officers can trace every figure back to its source data.
          </p>
        </Card>
        <Card className="p-6">
          <span className="rounded-full bg-info-bg px-3 py-1 text-xs font-semibold text-info">Pillar 3</span>
          <h2 className="mt-3 font-semibold">Market discipline</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-2">
            Explainable outputs support Pillar 3 disclosure expectations. The cross-reference agent produces integrated narratives
            that bridge quantitative metrics with qualitative risk language.
          </p>
        </Card>
      </div>

      <Card className="p-6">
        <h2 className="text-sm font-semibold">Agent → framework mapping</h2>
        <ul className="mt-4 grid gap-3 sm:grid-cols-2">
          {MAPPING.map(({ Icon, agent, maps }) => (
            <li key={agent} className="flex gap-3 rounded-xl bg-black/25 p-4">
              <Icon className="mt-0.5 size-5 shrink-0 text-brand-700" aria-hidden />
              <div><div className="text-sm font-medium">{agent}</div><div className="text-xs text-ink-3">{maps}</div></div>
            </li>
          ))}
        </ul>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-6">
          <div className="flex items-center gap-2"><ShieldCheck className="size-4 text-good" aria-hidden /><h2 className="text-sm font-semibold">Intended use</h2></div>
          <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-ink-2">{USES.map((u) => <li key={u}>{u}</li>)}</ul>
        </Card>
        <Card className="border-watch/30 p-6">
          <div className="flex items-center gap-2"><ShieldAlert className="size-4 text-watch" aria-hidden /><h2 className="text-sm font-semibold">Scope & limitations</h2></div>
          <p className="mt-3 text-sm leading-relaxed text-ink-2">
            This system does <b className="text-ink">not</b> calculate regulatory capital adequacy ratios, Tier 1 / Tier 2 capital
            buffers, LCR, NSFR or any other binding Basel III measure. It is not a substitute for regulatory reporting or
            prudential supervision.
          </p>
        </Card>
      </div>
    </div>
  );
}
