from __future__ import annotations
from typing import Any, Dict
from .schema import NormalizedCompanyRecord

def compute_saas_metrics(record: NormalizedCompanyRecord) -> Dict[str, Any]:
    """
    Computes SaaS specific metrics deterministically based on available data.
    Rule of 40 = Growth Rate (%) + Profit Margin (%)
    """
    if not record.revenue or len(record.revenue) < 2:
        return {"rule_of_40": None, "error": "Insufficient revenue data for SaaS metrics"}
        
    latest_rev = record.revenue[-1].value
    prev_rev = record.revenue[-2].value
    
    growth_rate = ((latest_rev - prev_rev) / prev_rev) * 100 if prev_rev > 0 else 0
    
    # Proxy Profit Margin for demo (assume 10%)
    profit_margin = 10.0
    
    rule_of_40 = growth_rate + profit_margin
    
    return {
        "growth_rate_pct": growth_rate,
        "profit_margin_pct": profit_margin,
        "rule_of_40": rule_of_40,
        "is_healthy": rule_of_40 >= 40.0
    }
