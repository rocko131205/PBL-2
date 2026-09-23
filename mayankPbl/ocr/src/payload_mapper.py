"""Payload mapper: converts raw ingestion payloads to NormalizedCompanyRecord.

Handles payloads from all sources (Bloomberg PDF, yfinance ticker, private CSV)
and produces the V2 NormalizedCompanyRecord with provenance tracking.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from .schema import NormalizedCompanyRecord, FinancialPeriod


# ── All fields that can be mapped from a time_series payload ──────────────

_FIELD_MAP: Dict[str, str] = {
    "revenue":                 "revenue",
    "cost_of_revenue":         "cost_of_revenue",
    "gross_profit":            "gross_profit",
    "operating_income":        "operating_income",
    "net_income":              "net_income",
    "ebitda":                  "ebitda",
    "interest_expense":        "interest_expense",
    "depreciation":            "depreciation",
    "pretax_income":           "pretax_income",
    "income_tax":              "income_tax",
    "operating_cash_flow":     "operating_cash_flow",
    "capital_expenditure":     "capital_expenditure",
    "free_cash_flow":          "free_cash_flow",
    "total_assets":            "total_assets",
    "total_liabilities":       "total_liabilities",
    "current_assets":          "current_assets",
    "current_liabilities":     "current_liabilities",
    "equity":                  "equity",
    "total_debt":              "total_debt",
    "long_term_debt":          "long_term_debt",
    "short_term_debt":         "short_term_debt",
    "cash_and_equivalents":    "cash_and_equivalents",
    "non_current_assets":      "non_current_assets",
    "non_current_liabilities": "non_current_liabilities",
    "retained_earnings":       "retained_earnings",
    "accounts_receivable":     "accounts_receivable",
    "inventory":               "inventory",
    "accounts_payable":        "accounts_payable",
    "basic_eps":               "basic_eps",
    "diluted_eps":             "diluted_eps",
}


def _map_series(ts: dict[str, Any], field_name: str) -> List[FinancialPeriod]:
    """Convert a raw time_series[field] array into a list of FinancialPeriod."""
    series = ts.get(field_name, [])
    if not isinstance(series, list):
        return []
    periods: List[FinancialPeriod] = []
    for item in series:
        if isinstance(item, dict) and "period" in item and "value" in item:
            val = item["value"]
            if val is not None:
                try:
                    periods.append(FinancialPeriod(period=str(item["period"]), value=float(val)))
                except (ValueError, TypeError):
                    pass
    return periods


def payload_to_normalized_record(
    payload: dict[str, Any],
    source_type: str = "unknown",
) -> NormalizedCompanyRecord:
    """Convert an ingestion payload (OCR / yfinance / CSV) to NormalizedCompanyRecord.

    V2: Tracks provenance for each field and supports new identity fields.
    """
    entity_dict = payload.get("entity") or {}
    entity_id = entity_dict.get("entity_id", "UNKNOWN")
    ts = payload.get("time_series") or {}

    # Build field-level provenance map
    source_provenance: Dict[str, str] = {}
    kwargs: Dict[str, Any] = {}

    for payload_field, record_field in _FIELD_MAP.items():
        periods = _map_series(ts, payload_field)
        if periods:
            kwargs[record_field] = periods
            source_provenance[record_field] = source_type

    # Map operating_income also to net_operating_income for DSCR compatibility
    if "operating_income" in kwargs and "net_operating_income" not in kwargs:
        kwargs["net_operating_income"] = kwargs["operating_income"]
        source_provenance["net_operating_income"] = source_type

    record = NormalizedCompanyRecord(
        entity_id=str(entity_id),
        source=source_type,
        currency=entity_dict.get("currency"),
        country=entity_dict.get("country"),
        industry=entity_dict.get("industry"),
        is_public=source_type == "ticker",
        ticker_symbol=entity_dict.get("source_files", [None])[0] if source_type == "ticker" else None,
        qualitative_context=entity_dict.get("qualitative_context", ""),
        source_provenance=source_provenance,
        **kwargs,
    )

    return record
