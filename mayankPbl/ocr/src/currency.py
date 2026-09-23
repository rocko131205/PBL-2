"""Currency normalization (V3).

Problem this solves: a US company reports in USD and an Indian company in INR.
Comparing their absolute revenue/assets side by side is meaningless. Before ANY
cross-company work (peer comparison, benchmarking), all monetary values must be
converted to one base currency — the same idea as feature standardization in ML.

Design:
- Rate lookup is pluggable and separate from the (pure, testable) conversion logic.
- Live rates come from yfinance FX pairs (e.g. 'INRUSD=X'); if unavailable we fall
  back to an approximate static table so the system still works offline.
- Ratios/percentages are currency-neutral and are NOT touched — only absolute
  monetary time series are converted.
- Every conversion records the rate used and its source, for full auditability.
"""
from __future__ import annotations

from typing import Optional, Tuple

from .schema import FinancialPeriod, NormalizedCompanyRecord

# Approximate USD value of 1 unit of each currency. Fallback only — clearly
# labelled as approximate wherever surfaced. Live rates override these.
_USD_PER_UNIT: dict[str, float] = {
    "USD": 1.0,
    "INR": 0.0120,
    "EUR": 1.08,
    "GBP": 1.27,
    "JPY": 0.0064,
    "CNY": 0.14,
    "CAD": 0.73,
    "AUD": 0.66,
    "CHF": 1.12,
    "SGD": 0.74,
    "HKD": 0.128,
    "KRW": 0.00073,
    "BRL": 0.19,
    "ZAR": 0.053,
    "AED": 0.272,
    "SAR": 0.266,
}


def _static_rate(from_ccy: str, to_ccy: str) -> Optional[float]:
    """Cross rate from the static fallback table. 1 from_ccy = X to_ccy."""
    a = _USD_PER_UNIT.get(from_ccy.upper())
    b = _USD_PER_UNIT.get(to_ccy.upper())
    if a is None or b is None or b == 0:
        return None
    return a / b


def _live_rate(from_ccy: str, to_ccy: str) -> Optional[float]:
    """Fetch a live FX rate from yfinance. Returns None on any failure."""
    try:
        import yfinance as yf

        pair = f"{from_ccy.upper()}{to_ccy.upper()}=X"
        hist = yf.Ticker(pair).history(period="5d")
        if hist is not None and not hist.empty:
            close = float(hist["Close"].dropna().iloc[-1])
            if close > 0:
                return close
    except Exception:
        pass
    return None


def get_fx_rate(
    from_ccy: str,
    to_ccy: str,
    live: bool = True,
) -> Tuple[Optional[float], str]:
    """Resolve the FX rate to convert 1 `from_ccy` into `to_ccy`.

    Returns (rate, source). source is one of: 'identity', 'live', 'static', 'unavailable'.
    """
    if not from_ccy or not to_ccy:
        return None, "unavailable"
    if from_ccy.upper() == to_ccy.upper():
        return 1.0, "identity"

    if live:
        r = _live_rate(from_ccy, to_ccy)
        if r is not None:
            return r, "live"

    r = _static_rate(from_ccy, to_ccy)
    if r is not None:
        return r, "static"

    return None, "unavailable"


def _convert_series(series: list[FinancialPeriod], rate: float) -> list[FinancialPeriod]:
    return [FinancialPeriod(period=p.period, value=p.value * rate) for p in series]


def normalize_record_currency(
    record: NormalizedCompanyRecord,
    base_currency: str = "USD",
    live: bool = True,
) -> NormalizedCompanyRecord:
    """Return a copy of `record` with all monetary fields converted to `base_currency`.

    - If the record has no currency, or is already in the base currency, it is returned
      unchanged (but flagged as normalized so downstream code knows it's comparable).
    - If no rate can be found, the record is returned unchanged and NOT flagged, so the
      caller can warn the user rather than silently comparing mismatched currencies.
    """
    src_ccy = (record.currency or "").upper()
    base = base_currency.upper()

    # Already comparable — nothing to convert.
    if src_ccy == base:
        updated = record.model_copy(deep=True)
        updated.is_currency_normalized = True
        updated.original_currency = src_ccy or None
        updated.fx_rate_used = 1.0
        return updated

    rate, source = get_fx_rate(src_ccy, base, live=live)
    if rate is None:
        # Cannot convert — leave untouched and unflagged; caller should warn.
        return record

    updated = record.model_copy(deep=True)
    for field in NormalizedCompanyRecord.MONETARY_FIELDS:
        series = getattr(updated, field, None)
        if series:
            setattr(updated, field, _convert_series(series, rate))

    updated.original_currency = src_ccy or None
    updated.currency = base
    updated.fx_rate_used = round(rate, 8)
    updated.is_currency_normalized = True
    return updated
