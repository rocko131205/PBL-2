"""Plain-language meanings for each metric (V3).

Answers "what does this number actually tell me?" for a non-specialist. One short
sentence per metric, focused on the credit/health interpretation — not the formula.
"""
from __future__ import annotations

from typing import Optional

MEANINGS: dict[str, str] = {
    # Profitability
    "gross_margin": "How much of each sales dollar is left after direct costs — higher means more room to cover everything else.",
    "operating_margin": "Profit from core operations per sales dollar, before interest and tax — the engine's efficiency.",
    "ebitda_margin": "Cash-like operating profit per sales dollar — a rough proxy for cash generation.",
    "net_profit_margin": "What's left as actual profit after everything, per sales dollar.",
    "net_margin": "What's left as actual profit after everything, per sales dollar.",
    "roe": "Profit generated on the owners' money — how hard equity is working.",
    "roa": "Profit generated on all assets — how efficiently the asset base is used.",
    "roce": "Return on the total capital (debt + equity) put to work in the business.",
    # Solvency / leverage
    "debt_to_equity": "How much debt the company carries per dollar of equity — higher means more financial risk.",
    "debt_to_assets": "Share of assets funded by debt rather than equity.",
    "equity_ratio": "Share of assets funded by the owners — a cushion against losses.",
    "financial_leverage": "How much the asset base is amplified by debt relative to equity.",
    "net_debt": "Total debt minus cash — the debt that would remain if all cash were used to repay it.",
    "net_debt_to_ebitda": "Years of operating cash-flow-like profit it would take to clear net debt — lower is safer.",
    "interest_coverage": "How many times operating profit covers the interest bill — higher is safer.",
    # Liquidity
    "current_ratio": "Whether short-term assets can cover short-term bills — above 1 is the baseline.",
    "quick_ratio": "Short-term coverage excluding inventory — a stricter liquidity test.",
    "working_capital": "Short-term assets minus short-term liabilities — day-to-day financial breathing room.",
    "cash_ratio": "Whether cash alone covers short-term bills — the strictest liquidity test.",
    # Debt service
    "dscr": "Whether cash covers loan payments — above 1 means it can pay, higher is safer.",
    # SaaS
    "saas_revenue_growth": "How fast revenue is growing year over year.",
    "saas_revenue_cagr_3yr": "Smoothed annual growth rate over three years.",
    "saas_revenue_stability": "How steady (vs erratic) revenue growth has been.",
    "saas_rule_of_40": "Growth % + profit margin % — a software health check; 40+ is considered healthy.",
    "saas_gross_margin": "Gross margin for the software business — software firms typically run high here.",
    "saas_operating_margin": "Operating margin for the software business.",
}


def meaning_for(metric_key: Optional[str]) -> str:
    """Return the plain-language meaning for a metric key, or empty string if unknown."""
    if not metric_key:
        return ""
    return MEANINGS.get(metric_key, "")
