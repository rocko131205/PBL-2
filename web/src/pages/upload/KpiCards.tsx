import { useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowDownRight, ArrowUpRight, History } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui";
import { Drawer } from "@/components/Drawer";
import { formatPercent, formatPeriod } from "@/lib/format";
import type { MetricCard } from "@/lib/types";

const ACCENT = "#7dd3fc";
const GRID = "#ffffff14";
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export function KpiCards({ cards }: { cards: MetricCard[] }) {
  const [open, setOpen] = useState<MetricCard | null>(null);
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((c) => <Kpi key={c.field} card={c} onOpen={() => setOpen(c)} />)}
      </div>
      <Drawer open={!!open} title={open ? `${open.label} — full history` : ""} onClose={() => setOpen(null)}>
        {open && <HistoryBody card={open} />}
      </Drawer>
    </>
  );
}

function Kpi({ card, onOpen }: { card: MetricCard; onOpen: () => void }) {
  const { change_pct: change } = card;
  // For liabilities, growth isn't "good" or "bad" by itself, so it stays neutral.
  const neutral = card.field === "total_liabilities";
  const up = (change ?? 0) >= 0;
  return (
    <Card className="flex flex-col p-5">
      <div className="text-sm text-ink-2">{card.label}</div>
      <div className="num mt-2 text-2xl font-semibold tracking-tight">{card.display}</div>
      <div className="mt-1 flex items-center gap-2 text-xs text-ink-3">
        <span>{formatPeriod(card.period)} · latest</span>
        {change != null && (
          <span className={clsx("inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 font-medium",
            neutral ? "bg-white/10 text-ink-2" : up ? "bg-good-bg text-good" : "bg-risk-bg text-risk")}
            title="Change from the first to the latest period">
            {up ? <ArrowUpRight className="size-3" aria-hidden /> : <ArrowDownRight className="size-3" aria-hidden />}
            {formatPercent(Math.abs(change), 1)}
          </span>
        )}
      </div>
      {card.series.length >= 2 && (
        <div className="mt-3 h-12" aria-hidden>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={card.series} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={`spark-${card.field}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor={ACCENT} stopOpacity={0.35} />
                  <stop offset="1" stopColor={ACCENT} stopOpacity={0} />
                </linearGradient>
              </defs>
              <YAxis hide domain={["dataMin", "dataMax"]} />
              <Area type="monotone" dataKey="value" stroke={ACCENT} strokeWidth={2} fill={`url(#spark-${card.field})`} dot={false} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
      {card.series.length > 0 && (
        <button onClick={onOpen} className="mt-3 inline-flex items-center gap-1.5 self-start text-xs font-medium text-brand-700 hover:underline">
          <History className="size-3.5" aria-hidden /> All {card.series.length} periods
        </button>
      )}
    </Card>
  );
}

/** Drawer body: the period table, a line chart, and the first → latest summary. */
function HistoryBody({ card }: { card: MetricCard }) {
  const rows = card.series;
  const first = rows[0], last = rows[rows.length - 1];
  return (
    <div className="space-y-6">
      {rows.length >= 2 && (
        <div className="h-56" role="img" aria-label={`${card.label} by period`}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="period" tickFormatter={formatPeriod} stroke="#8590a0" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(v: number) => compact.format(v)} stroke="#8590a0" fontSize={11} tickLine={false} axisLine={false} width={52} />
              <Tooltip
                contentStyle={{ background: "#0f141c", border: "1px solid #ffffff26", borderRadius: 12, fontSize: 12 }}
                labelFormatter={(p) => formatPeriod(String(p))}
                formatter={(_v, _n, item) => [(item.payload as { display: string }).display, card.label]}
              />
              <Line type="monotone" dataKey="value" stroke={ACCENT} strokeWidth={2.2} dot={{ r: 3, fill: ACCENT }} activeDot={{ r: 5 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      {rows.length >= 2 && card.change_pct != null && (
        <p className="text-sm text-ink-2">
          {formatPeriod(first.period)} → {formatPeriod(last.period)}: <span className="num text-ink">{first.display}</span> →{" "}
          <span className="num text-ink">{last.display}</span> ({card.change_pct >= 0 ? "+" : "−"}{formatPercent(Math.abs(card.change_pct), 1)}).
        </p>
      )}
      <table className="w-full text-sm">
        <thead><tr className="border-b border-line text-left text-xs text-ink-3"><th className="py-2 font-medium">Period</th><th className="py-2 text-right font-medium">Value</th></tr></thead>
        <tbody>
          {[...rows].reverse().map((r) => (
            <tr key={r.period} className="border-b border-line/60"><td className="py-2.5">{formatPeriod(r.period)}</td><td className="num py-2.5 text-right">{r.display}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
