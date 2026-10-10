import { formatMoney, formatPercent, formatPeriod, formatRatio } from "./format";

describe("formatMoney (mirrors finveritas/shared/formatting.py)", () => {
  it("uses lakh/crore for INR", () => {
    expect(formatMoney(2553000, "INR")).toBe("₹25.53 L");
    // Same western digit grouping as the Python formatter (not 1,48,903).
    expect(formatMoney(148903e7, "INR")).toBe("₹148,903.00 Cr");
    expect(formatMoney(5000, "INR")).toBe("₹5,000.00");
  });
  it("uses K/M/B/T for other currencies", () => {
    expect(formatMoney(1_200_000, "USD")).toBe("$1.20M");
    expect(formatMoney(256_345_567_000, "USD")).toBe("$256.35B");
    expect(formatMoney(950, "USD")).toBe("$950.00");
  });
  it("handles negatives, nulls and unknown currencies", () => {
    expect(formatMoney(-2_500_000, "USD")).toBe("-$2.50M");
    expect(formatMoney(null)).toBe("N/A");
    expect(formatMoney(1500, "XYZ")).toBe("XYZ 1.50K");
  });
});

describe("other formatters", () => {
  it("ratio / percent", () => {
    expect(formatRatio(1.8456)).toBe("1.85x");
    expect(formatPercent(42.54)).toBe("42.5%");
    expect(formatRatio(undefined)).toBe("N/A");
  });
  it("period labels", () => {
    expect(formatPeriod("2025-FY")).toBe("FY 2025");
    expect(formatPeriod("2024-Q3")).toBe("Q3 2024");
    expect(formatPeriod("weird")).toBe("weird");
  });
});
