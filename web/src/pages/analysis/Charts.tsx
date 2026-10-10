import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "@/components/ui";
import { C, axis, compact, tooltip } from "@/components/chart";
import { formatMoney, formatPercent, formatPeriod } from "@/lib/format";
import type { Peer, Report, Trends } from "@/lib/analysis";

/* ── Trends ─────────────────────────────────────────────────────────────── */

export function TrendsSection({ trends, currency }: { trends: Trends; currency: string | null }) {
  const { revenue, margin } = trends;
  const money = (v: unknown) => formatMoney(Number(v), currency);
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <Card className="p-5 sm:p-6">
        <h3 className="text-sm font-semibold">Revenue — history and 3-year forecast</h3>
        <div className="mt-4 h-72" role="img" aria-label="Revenue history and forecast scenarios">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={revenue.rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="hist" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor={C.accent} stopOpacity={0.3} />
                  <stop offset="1" stopColor={C.accent} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="period" tickFormatter={formatPeriod} {...axis} />
              <YAxis tickFormatter={(v: number) => compact.format(v)} width={56} {...axis} />
              <Tooltip {...tooltip} labelFormatter={(p) => formatPeriod(String(p))}
                formatter={(v, name) => [Array.isArray(v) ? `${money(v[0])} – ${money(v[1])}` : money(v), name]} />
              <Legend wrapperStyle={{ fontSize: 12, color: C.muted }} />
              <Area dataKey="band" name="Scenario range" stroke="none" fill={C.accentStrong} fillOpacity={0.15} isAnimationActive={false} />
              <Area dataKey="history" name="Actual" type="monotone" stroke={C.accent} strokeWidth={2.4} fill="url(#hist)" dot={{ r: 3, fill: C.accent }} isAnimationActive={false} connectNulls />
              <Line dataKey="base" name="Base" type="monotone" stroke={C.accentSoft} strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} connectNulls />
              <Line dataKey="optimistic" name="Optimistic" type="monotone" stroke={C.good} strokeWidth={1.5} strokeDasharray="2 4" dot={false} isAnimationActive={false} connectNulls />
              <Line dataKey="pessimistic" name="Pessimistic" type="monotone" stroke={C.risk} strokeWidth={1.5} strokeDasharray="2 4" dot={false} isAnimationActive={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        {revenue.cagr_pct != null && (
          <p className="mt-3 text-sm text-ink-2">
            Historical growth <b className="text-ink">{formatPercent(revenue.cagr_pct)}/yr</b>. The base case grows at that rate;
            optimistic {formatPercent(revenue.optimistic_growth_pct)}, pessimistic {formatPercent(revenue.pessimistic_growth_pct)}.
            {revenue.latest_display && <> Latest actual: <span className="num text-ink">{revenue.latest_display}</span>.</>}
          </p>
        )}
      </Card>

      <Card className="p-5 sm:p-6">
        <h3 className="text-sm font-semibold">Operating margin</h3>
        {margin ? (
          <>
            <div className="mt-4 h-72" role="img" aria-label="Operating margin by period">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={margin.rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={C.grid} vertical={false} />
                  <XAxis dataKey="period" tickFormatter={formatPeriod} {...axis} />
                  <YAxis tickFormatter={(v: number) => `${v}%`} width={44} {...axis} />
                  <Tooltip {...tooltip} labelFormatter={(p) => formatPeriod(String(p))} formatter={(v) => [formatPercent(Number(v), 2), "Operating margin"]} />
                  <Line dataKey="margin" type="monotone" stroke={margin.trend === "declining" ? C.risk : C.good} strokeWidth={2.4} dot={{ r: 3 }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-3 text-sm text-ink-2">
              Margin is <b className={margin.trend === "declining" ? "text-risk" : margin.trend === "improving" ? "text-good" : "text-ink"}>{margin.trend}</b>:{" "}
              {formatPercent(margin.first)} → {formatPercent(margin.last)} across the period.
            </p>
          </>
        ) : (
          <p className="mt-3 text-sm text-ink-3">Not enough matching revenue and operating-income periods to chart the margin.</p>
        )}
      </Card>
    </div>
  );
}

/* ── Peers ──────────────────────────────────────────────────────────────── */

const METRIC_LABELS: Record<string, string> = {
  revenue_growth: "Revenue growth", operating_margin: "Operating margin", gross_margin: "Gross margin",
  rule_of_40: "Rule of 40", debt_to_equity: "Debt / equity", current_ratio: "Current ratio",
};
const pct = (v?: number | null, suffix = "%") => (v == null ? "—" : `${v.toFixed(1)}${suffix}`);

export function PeersSection({ peers, metrics }: { peers: Peer[]; metrics: Report["peer_metrics"] }) {
  const chart = Object.entries(metrics)
    .filter(([, m]) => m.target != null && m.peer_median != null)
    .map(([k, m]) => ({ metric: METRIC_LABELS[k] ?? k.replace(/_/g, " "), Company: m.target, "Peer median": m.peer_median }));

  if (peers.length === 0) {
    return <Card className="p-6 text-sm text-ink-3">No comparable peers with live data were found for this company.</Card>;
  }
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      {chart.length > 0 && (
        <Card className="p-5 sm:p-6">
          <h3 className="text-sm font-semibold">Company vs peer median</h3>
          <div className="mt-4 h-72" role="img" aria-label="Company metrics compared with the peer median">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="metric" {...axis} interval={0} tick={{ fontSize: 11 }} />
                <YAxis width={44} {...axis} />
                <Tooltip {...tooltip} cursor={{ fill: "#ffffff0a" }} formatter={(v, n) => [Number(v).toFixed(2), n]} />
                <Legend wrapperStyle={{ fontSize: 12, color: C.muted }} />
                <Bar dataKey="Company" fill={C.accentStrong} radius={[6, 6, 0, 0]} />
                <Bar dataKey="Peer median" fill={C.muted} radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-ink-3">
              <tr className="border-b border-line">
                <th className="px-4 py-3 font-medium">Company</th>
                <th className="px-4 py-3 text-right font-medium">Growth</th>
                <th className="px-4 py-3 text-right font-medium">Op. margin</th>
                <th className="px-4 py-3 text-right font-medium">Gross margin</th>
                <th className="px-4 py-3 text-right font-medium">D/E</th>
              </tr>
            </thead>
            <tbody>
              {peers.map((p) => (
                <tr key={`${p.entity_id}-${p.ticker}`} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-3">
                    <div className="font-medium">{p.entity_id} <span className="text-xs text-ink-3">{p.ticker}</span></div>
                    <span className={p.peer_tier === "primary" ? "text-[11px] text-brand-700" : "text-[11px] text-ink-3"}>
                      {p.peer_tier === "primary" ? "Primary peer" : "Secondary peer"}
                    </span>
                  </td>
                  <td className="num px-4 py-3 text-right">{pct(p.revenue_growth)}</td>
                  <td className="num px-4 py-3 text-right">{pct(p.operating_margin)}</td>
                  <td className="num px-4 py-3 text-right">{pct(p.gross_margin)}</td>
                  <td className="num px-4 py-3 text-right">{pct(p.debt_to_equity, "x")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
