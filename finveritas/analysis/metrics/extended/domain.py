"""Sector-specific metrics (SaaS / banking / retail / manufacturing).

Ported from DeterminX ``metrics/domain.py``. Standard statements carry no customer
counts, churn, NPAs or plant capacity, so those inputs arrive through the
record's ``domain_inputs`` and any metric without its inputs is reported as
``REQUIRES_ADDITIONAL_DOCUMENT`` naming exactly what would unlock it. Nothing is
ever fabricated. ``sector == "general"`` (the default) produces no entries.

Rule of 40 is NOT recomputed here: ``saas.py`` already produces ``saas_rule_of_40``.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from finveritas.shared.schema import FactLedgerEntry, NormalizedCompanyRecord

from . import _util as u

CATEGORY = "domain"
SECTORS = ("general", "saas", "banking", "retail", "manufacturing")

# Operational inputs each sector understands, for the UI form.
DOMAIN_INPUT_FIELDS: Dict[str, List[str]] = {
    "saas": ["sales_marketing_expense", "new_customers", "recurring_revenue", "total_customers",
             "churn_rate_pct", "beginning_arr", "expansion_revenue", "churned_revenue"],
    "banking": ["interest_income", "interest_expense_on_funds", "avg_earning_assets", "gross_npa",
                "gross_advances", "casa_deposits", "total_deposits", "capital_adequacy_ratio_pct"],
    "retail": ["same_store_revenue_current", "same_store_revenue_prior", "total_orders", "retail_area_sqft"],
    "manufacturing": ["installed_capacity_units", "actual_output_units", "order_book_value"],
}


def _have(inp: Dict[str, float], *keys: str) -> bool:
    return all(k in inp for k in keys)


def _ratio(num: float, den: float) -> Optional[float]:
    return num / den if den else None


def _derived(metric: str, name: str, value: Optional[float], unit: str, formula: str,
             inputs: List[str], missing_reason: str) -> FactLedgerEntry:
    if value is None:
        return u.requires_document(metric, name, CATEGORY, missing_reason, formula)
    return u.entry(metric, name, CATEGORY, value, unit, u.MULTI, formula + " (from supplied operational inputs)", inputs)


def _saas(record: NormalizedCompanyRecord, inp: Dict[str, float]) -> List[FactLedgerEntry]:
    out: List[FactLedgerEntry] = []
    ccy = record.currency or "currency"

    periods = u.common_periods(record, ["rd_expense", "revenue"])
    if periods:
        p = periods[-1]
        rev = u.series(record, "revenue")[p]
        if rev:
            out.append(u.entry("rd_intensity", "R&D Intensity", CATEGORY, u.series(record, "rd_expense")[p] / rev * 100,
                               "%", p, "R&D Expense / Revenue x 100", ["rd_expense", "revenue"]))
    else:
        out.append(u.unavailable("rd_intensity", "R&D Intensity", CATEGORY, "Needs R&D expense and revenue."))

    cac = _ratio(inp["sales_marketing_expense"], inp["new_customers"]) if _have(inp, "sales_marketing_expense", "new_customers") else None
    out.append(_derived("cac", "Customer Acquisition Cost (CAC)", cac, f"{ccy}/customer",
                        "Sales & Marketing Expense / New Customers", ["sales_marketing_expense", "new_customers"],
                        "Needs operational inputs 'sales_marketing_expense' and 'new_customers' (not in a financial statement)."))

    arpu = _ratio(inp["recurring_revenue"], inp["total_customers"]) if _have(inp, "recurring_revenue", "total_customers") else None
    out.append(_derived("arpu", "ARPU", arpu, f"{ccy}/customer", "Recurring Revenue / Total Customers",
                        ["recurring_revenue", "total_customers"],
                        "Needs operational inputs 'recurring_revenue' and 'total_customers'."))

    gm_periods = u.common_periods(record, ["revenue", "gross_profit"])
    gm = None
    if gm_periods:
        rev = u.series(record, "revenue")[gm_periods[-1]]
        gm = _ratio(u.series(record, "gross_profit")[gm_periods[-1]], rev)

    churn = inp.get("churn_rate_pct")
    ltv = arpu * gm / (churn / 100.0) if arpu is not None and gm is not None and churn else None
    out.append(_derived("ltv", "Customer Lifetime Value (LTV)", ltv, f"{ccy}/customer",
                        "(ARPU x Gross Margin) / Churn Rate", ["recurring_revenue", "total_customers", "churn_rate_pct"],
                        "Needs ARPU, a computable gross margin and the operational input 'churn_rate_pct'."))
    out.append(_derived("ltv_to_cac_ratio", "LTV / CAC", _ratio(ltv, cac) if ltv is not None and cac else None, "ratio",
                        "LTV / CAC", ["ltv", "cac"], "Needs both LTV and CAC."))
    payback = None
    if cac and arpu is not None and gm:
        monthly = arpu * gm / 12.0
        payback = _ratio(cac, monthly)
    out.append(_derived("cac_payback_months", "CAC Payback", payback, "months", "CAC / (ARPU x Gross Margin / 12)",
                        ["cac", "arpu"], "Needs CAC, ARPU and a gross margin."))

    nrr = None
    if _have(inp, "beginning_arr", "expansion_revenue", "churned_revenue") and inp["beginning_arr"] > 0:
        nrr = (inp["beginning_arr"] + inp["expansion_revenue"] - inp["churned_revenue"]) / inp["beginning_arr"] * 100
    out.append(_derived("net_revenue_retention", "Net Revenue Retention", nrr, "%",
                        "(Beginning ARR + Expansion - Churned) / Beginning ARR x 100",
                        ["beginning_arr", "expansion_revenue", "churned_revenue"],
                        "Needs operational inputs 'beginning_arr', 'expansion_revenue' and 'churned_revenue'."))
    return out


def _banking(inp: Dict[str, float]) -> List[FactLedgerEntry]:
    nim = None
    if _have(inp, "interest_income", "interest_expense_on_funds", "avg_earning_assets") and inp["avg_earning_assets"] > 0:
        nim = (inp["interest_income"] - inp["interest_expense_on_funds"]) / inp["avg_earning_assets"] * 100
    npa = _ratio(inp["gross_npa"], inp["gross_advances"]) if _have(inp, "gross_npa", "gross_advances") else None
    casa = _ratio(inp["casa_deposits"], inp["total_deposits"]) if _have(inp, "casa_deposits", "total_deposits") else None
    car = inp.get("capital_adequacy_ratio_pct")
    return [
        _derived("net_interest_margin", "Net Interest Margin", nim, "%",
                 "(Interest Income - Interest Expense on Funds) / Average Earning Assets x 100",
                 ["interest_income", "interest_expense_on_funds", "avg_earning_assets"],
                 "Needs 'interest_income', 'interest_expense_on_funds' and 'avg_earning_assets'."),
        _derived("gross_npa_ratio", "Gross NPA Ratio", npa * 100 if npa is not None else None, "%",
                 "Gross NPA / Gross Advances x 100", ["gross_npa", "gross_advances"],
                 "Needs 'gross_npa' and 'gross_advances'."),
        _derived("casa_ratio", "CASA Ratio", casa * 100 if casa is not None else None, "%",
                 "CASA Deposits / Total Deposits x 100", ["casa_deposits", "total_deposits"],
                 "Needs 'casa_deposits' and 'total_deposits'."),
        _derived("capital_adequacy_ratio", "Capital Adequacy Ratio", car, "%", "As disclosed (regulatory figure)",
                 ["capital_adequacy_ratio_pct"],
                 "A regulatory disclosure that cannot be derived from statements; supply 'capital_adequacy_ratio_pct'."),
    ]


def _retail(record: NormalizedCompanyRecord, inp: Dict[str, float]) -> List[FactLedgerEntry]:
    latest = u.latest_point(u.series(record, "revenue"))
    sss = None
    if _have(inp, "same_store_revenue_current", "same_store_revenue_prior") and inp["same_store_revenue_prior"] > 0:
        sss = (inp["same_store_revenue_current"] - inp["same_store_revenue_prior"]) / inp["same_store_revenue_prior"] * 100
    aov = _ratio(latest[1], inp["total_orders"]) if latest and "total_orders" in inp else None
    spsf = _ratio(latest[1], inp["retail_area_sqft"]) if latest and "retail_area_sqft" in inp else None
    return [
        _derived("same_store_sales_growth", "Same-Store Sales Growth", sss, "%",
                 "(Same-store revenue current - prior) / prior x 100",
                 ["same_store_revenue_current", "same_store_revenue_prior"],
                 "Needs 'same_store_revenue_current' and 'same_store_revenue_prior' (store-level disclosure)."),
        _derived("average_order_value", "Average Order Value", aov, "absolute", "Latest revenue / total orders",
                 ["revenue", "total_orders"], "Needs revenue and the operational input 'total_orders'."),
        _derived("sales_per_sqft", "Sales per Sq Ft", spsf, "absolute", "Latest revenue / retail area (sq ft)",
                 ["revenue", "retail_area_sqft"], "Needs revenue and the operational input 'retail_area_sqft'."),
    ]


def _manufacturing(record: NormalizedCompanyRecord, inp: Dict[str, float]) -> List[FactLedgerEntry]:
    cap = None
    if _have(inp, "installed_capacity_units", "actual_output_units") and inp["installed_capacity_units"] > 0:
        cap = inp["actual_output_units"] / inp["installed_capacity_units"] * 100
    latest = u.latest_point(u.series(record, "revenue"))
    ob = _ratio(inp["order_book_value"], latest[1]) if latest and "order_book_value" in inp else None
    return [
        _derived("capacity_utilization", "Capacity Utilization", cap, "%", "Actual output / installed capacity x 100",
                 ["installed_capacity_units", "actual_output_units"],
                 "Needs 'installed_capacity_units' and 'actual_output_units' (plant disclosure)."),
        _derived("order_book_to_revenue", "Order Book / Revenue", ob, "ratio", "Order book value / latest revenue",
                 ["order_book_value", "revenue"], "Needs revenue and the operational input 'order_book_value'."),
    ]


def compute_domain(record: NormalizedCompanyRecord) -> List[FactLedgerEntry]:
    sector = (record.sector or "general").strip().lower()
    if sector in ("", "general", "none"):
        return []
    inp = {k: float(v) for k, v in (record.domain_inputs or {}).items()}
    if sector == "saas":
        return _saas(record, inp)
    if sector == "banking":
        return _banking(inp)
    if sector == "retail":
        return _retail(record, inp)
    if sector == "manufacturing":
        return _manufacturing(record, inp)
    return [u.unavailable("sector_metrics", "Sector metrics", CATEGORY,
                          f"Unknown sector '{sector}'. Supported: {', '.join(SECTORS[1:])}.")]
