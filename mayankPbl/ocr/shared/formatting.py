"""Human-readable formatting for money and metrics (V3).

Fixes the old display bug where a value like 256,345,567,000 was shown as
"256,345,567M" (millions applied on top of an already-large number, with no
currency symbol). Here we auto-scale to K / M / B / T and attach a currency symbol.
"""
from __future__ import annotations

from typing import Optional

_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "JPY": "¥",
    "CNY": "¥", "CAD": "C$", "AUD": "A$", "CHF": "CHF ", "SGD": "S$",
    "HKD": "HK$", "KRW": "₩", "BRL": "R$", "ZAR": "R", "AED": "AED ", "SAR": "SAR ",
}


def currency_symbol(currency: Optional[str]) -> str:
    if not currency:
        return ""
    return _CURRENCY_SYMBOLS.get(currency.upper(), f"{currency.upper()} ")


# Currencies that conventionally use the Indian lakh/crore system.
_LAKH_CRORE_CCY = {"INR", "PKR", "LKR", "NPR", "BDT"}


def format_money(value: Optional[float], currency: Optional[str] = None, decimals: int = 2) -> str:
    """Format a monetary value with country-appropriate scaling.

    - INR (and other South-Asian currencies): lakh (L) / crore (Cr) — e.g. '₹1,48,903 Cr'.
    - Everyone else: K / M / B / T — e.g. '$1.20M', '₹256.3B'.
    Returns 'N/A' for None.
    """
    if value is None:
        return "N/A"

    sym = currency_symbol(currency)
    sign = "-" if value < 0 else ""
    v = abs(float(value))
    ccy = (currency or "").upper()

    if ccy in _LAKH_CRORE_CCY:
        if v >= 1e7:      # >= 1 crore
            return f"{sign}{sym}{v / 1e7:,.{decimals}f} Cr"
        if v >= 1e5:      # >= 1 lakh
            return f"{sign}{sym}{v / 1e5:,.{decimals}f} L"
        return f"{sign}{sym}{v:,.{decimals}f}"

    if v >= 1e12:
        scaled, suffix = v / 1e12, "T"
    elif v >= 1e9:
        scaled, suffix = v / 1e9, "B"
    elif v >= 1e6:
        scaled, suffix = v / 1e6, "M"
    elif v >= 1e3:
        scaled, suffix = v / 1e3, "K"
    else:
        return f"{sign}{sym}{v:,.{decimals}f}"

    return f"{sign}{sym}{scaled:,.{decimals}f}{suffix}"


def format_ratio(value: Optional[float], suffix: str = "x", decimals: int = 2) -> str:
    """Format a ratio like DSCR ('1.85x') or debt-to-equity ('0.42x')."""
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}{suffix}"


def format_percent(value: Optional[float], decimals: int = 1) -> str:
    """Format a percentage. Expects the value already in percent units (e.g. 42.5 -> '42.5%')."""
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}%"
