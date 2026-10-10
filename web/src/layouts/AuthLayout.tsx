import type { ReactNode } from "react";
import { Wordmark } from "@/components/Brand";

interface Props {
  title: string;
  subtitle?: string;
  children: ReactNode;
}

export function AuthLayout({ title, subtitle, children }: Props) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      <main className="flex flex-col px-5 py-8 sm:px-12">
        <Wordmark />
        <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center py-8">
          <div className="glass rounded-3xl p-7 sm:p-9">
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            {subtitle && <p className="mt-1.5 text-sm text-ink-2">{subtitle}</p>}
            <div className="mt-7">{children}</div>
          </div>
        </div>
        <p className="text-center text-xs text-ink-3">FinVeritas · Secure · Explainable · Auditable</p>
      </main>

      <aside className="hidden items-center justify-center px-10 py-14 lg:flex" aria-label="Product preview">
        <Preview />
      </aside>
    </div>
  );
}

/* A decorative, clearly-labelled sample of what the product produces. */
function Preview() {
  return (
    <div className="w-full max-w-xl" aria-hidden>
      <p className="accent-text text-sm font-medium">Credit analysis you can trace to the source</p>
      <h2 className="mt-2 text-4xl font-semibold leading-tight tracking-tight">
        Every ratio computed in code.<br />
        <span className="text-ink-2">The AI only explains it.</span>
      </h2>

      <div className="mt-9 grid grid-cols-5 gap-4">
        {/* Grade */}
        <div className="glass col-span-2 rounded-2xl p-5">
          <div className="text-xs text-ink-3">Credit grade</div>
          <div className="accent-text mt-1 text-5xl font-semibold">BBB</div>
          <div className="mt-1 text-xs text-ink-2">Adequate · composite 72/100</div>
          <div className="mt-4 space-y-2">
            {[["Leverage", 78, "bg-good"], ["Liquidity", 64, "bg-watch"], ["Profitability", 81, "bg-good"]].map(([n, v, c]) => (
              <div key={n as string}>
                <div className="flex justify-between text-[11px] text-ink-2"><span>{n}</span><span className="num">{v}</span></div>
                <div className="mt-1 h-1.5 rounded-full bg-white/10"><div className={`h-full rounded-full ${c}`} style={{ width: `${v}%` }} /></div>
              </div>
            ))}
          </div>
        </div>

        {/* Credibility */}
        <div className="glass col-span-3 flex items-center gap-5 rounded-2xl p-5">
          <svg viewBox="0 0 80 80" className="size-24 shrink-0 -rotate-90">
            <circle cx="40" cy="40" r="32" fill="none" stroke="#ffffff14" strokeWidth="8" />
            <circle cx="40" cy="40" r="32" fill="none" stroke="#34d399" strokeWidth="8" strokeLinecap="round"
              strokeDasharray={`${0.92 * 2 * Math.PI * 32} ${2 * Math.PI * 32}`} />
          </svg>
          <div>
            <div className="text-xs text-ink-3">Data credibility</div>
            <div className="num text-3xl font-semibold">92<span className="text-base text-ink-3"> / 100</span></div>
            <div className="mt-1 inline-flex rounded-full bg-good-bg px-2.5 py-0.5 text-[11px] font-medium text-good">High confidence</div>
            <div className="mt-2 text-[11px] text-ink-3">9 checks · accounting identity passed</div>
          </div>
        </div>

        {/* DSCR chart */}
        <div className="glass col-span-5 rounded-2xl p-5">
          <div className="flex items-baseline justify-between">
            <div>
              <div className="text-xs text-ink-3">Debt service coverage by year</div>
              <div className="num mt-1 text-2xl font-semibold">1.42x <span className="text-xs font-normal text-ink-3">minimum, year 3</span></div>
            </div>
            <div className="flex gap-1.5">
              {["Base", "Stress"].map((t, i) => (
                <span key={t} className={`rounded-full px-3 py-1 text-[11px] ${i === 0 ? "accent-gradient text-white" : "border border-line-strong text-ink-2"}`}>{t}</span>
              ))}
            </div>
          </div>
          <svg viewBox="0 0 400 110" className="mt-3 w-full">
            <defs>
              <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#60a5fa" stopOpacity="0.35" />
                <stop offset="1" stopColor="#60a5fa" stopOpacity="0" />
              </linearGradient>
            </defs>
            <line x1="0" x2="400" y1="78" y2="78" stroke="#fb7185" strokeDasharray="4 4" strokeOpacity="0.7" />
            <text x="396" y="73" textAnchor="end" fontSize="9" fill="#fb7185">1.0x</text>
            <path d="M0 40 C40 30 70 50 110 44 S180 20 220 52 S300 36 340 30 S385 22 400 26 L400 110 L0 110Z" fill="url(#area)" />
            <path d="M0 40 C40 30 70 50 110 44 S180 20 220 52 S300 36 340 30 S385 22 400 26" fill="none" stroke="#7dd3fc" strokeWidth="2.2" />
            <circle cx="220" cy="52" r="4.5" fill="#fff" stroke="#3b82f6" strokeWidth="2" />
          </svg>
        </div>
      </div>
      <p className="mt-3 text-[11px] text-ink-3">Illustrative sample data</p>
    </div>
  );
}
