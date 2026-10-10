export function BrandMark({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="fv-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#38bdf8" />
          <stop offset="1" stopColor="#1d4ed8" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#fv-g)" />
      <path d="M10 22V10h10.5v3H13.5v2H19v3h-5.5v4z" fill="#fff" />
      <circle cx="24" cy="22" r="2.2" fill="#34d399" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark />
      <div className="leading-tight">
        <div className="text-base font-semibold tracking-tight text-ink">FinVeritas</div>
        <div className="text-[11px] text-ink-3">Explainable financial analysis</div>
      </div>
    </div>
  );
}
