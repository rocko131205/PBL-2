/** Port of finveritas/shared/formatting.py — keep the two in sync. */

const SYMBOLS: Record<string, string> = {
  USD: "$", INR: "₹", EUR: "€", GBP: "£", JPY: "¥", CNY: "¥", CAD: "C$", AUD: "A$",
  CHF: "CHF ", SGD: "S$", HKD: "HK$", KRW: "₩", BRL: "R$", ZAR: "R", AED: "AED ", SAR: "SAR ",
};
const LAKH_CRORE = new Set(["INR", "PKR", "LKR", "NPR", "BDT"]);

export function currencySymbol(currency?: string | null): string {
  if (!currency) return "";
  return SYMBOLS[currency.toUpperCase()] ?? `${currency.toUpperCase()} `;
}

const fixed = (n: number, d: number) =>
  n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

export function formatMoney(value?: number | null, currency?: string | null, decimals = 2): string {
  if (value == null || Number.isNaN(value)) return "N/A";
  const sym = currencySymbol(currency);
  const sign = value < 0 ? "-" : "";
  const v = Math.abs(value);
  const ccy = (currency ?? "").toUpperCase();

  if (LAKH_CRORE.has(ccy)) {
    if (v >= 1e7) return `${sign}${sym}${fixed(v / 1e7, decimals)} Cr`;
    if (v >= 1e5) return `${sign}${sym}${fixed(v / 1e5, decimals)} L`;
    return `${sign}${sym}${fixed(v, decimals)}`;
  }
  const steps: [number, string][] = [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]];
  for (const [limit, suffix] of steps) {
    if (v >= limit) return `${sign}${sym}${fixed(v / limit, decimals)}${suffix}`;
  }
  return `${sign}${sym}${fixed(v, decimals)}`;
}

export function formatRatio(value?: number | null, suffix = "x", decimals = 2): string {
  return value == null ? "N/A" : `${value.toFixed(decimals)}${suffix}`;
}

export function formatPercent(value?: number | null, decimals = 1): string {
  return value == null ? "N/A" : `${value.toFixed(decimals)}%`;
}

/** '2025-FY' -> 'FY 2025', '2024-Q3' -> 'Q3 2024'; anything else is returned unchanged. */
export function formatPeriod(period?: string | null): string {
  if (!period || period === "—") return "—";
  const year = period.slice(0, 4);
  if (!/^\d{4}$/.test(year)) return period;
  const tail = period.slice(5);
  if (tail.toUpperCase() === "FY") return `FY ${year}`;
  if (tail && tail[0].toUpperCase() === "Q") return `${tail.toUpperCase()} ${year}`;
  return period;
}
