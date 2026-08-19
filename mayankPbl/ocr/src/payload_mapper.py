from __future__ import annotations
from typing import Any
from .schema import NormalizedCompanyRecord, FinancialPeriod

def payload_to_normalized_record(payload: dict[str, Any], source_type: str = "unknown") -> NormalizedCompanyRecord:
    """
    Converts the OCR JSON payload into the V2 NormalizedCompanyRecord.
    """
    entity_dict = payload.get("entity") or {}
    entity_id = entity_dict.get("entity_id", "UNKNOWN")
    ts = payload.get("time_series") or {}
    
    def _map_series(field_name: str) -> list[FinancialPeriod]:
        series = ts.get(field_name, [])
        if not isinstance(series, list):
            return []
        periods = []
        for item in series:
            if isinstance(item, dict) and "period" in item and "value" in item:
                val = item["value"]
                if val is not None:
                    try:
                        periods.append(FinancialPeriod(period=str(item["period"]), value=float(val)))
                    except ValueError:
                        pass
        return periods
    
    record = NormalizedCompanyRecord(
        entity_id=str(entity_id),
        source=source_type,
        currency=entity_dict.get("currency", "USD"),
        qualitative_context=entity_dict.get("qualitative_context", ""),
        revenue=_map_series("revenue"),
        net_operating_income=_map_series("operating_income"), 
        total_assets=_map_series("total_assets"),
        total_liabilities=_map_series("total_liabilities"),
        current_assets=_map_series("current_assets"),
        current_liabilities=_map_series("current_liabilities"),
        equity=_map_series("equity")
    )
    
    return record
