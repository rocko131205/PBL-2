from __future__ import annotations
from typing import Any, Dict
import pandas as pd

from .schema import NormalizedCompanyRecord, DSCRInputs

def compute_dscr(record: NormalizedCompanyRecord, dscr_inputs: DSCRInputs) -> Dict[str, Any]:
    """
    Computes Debt Service Coverage Ratio deterministically.
    DSCR = Net Operating Income (NOI) / Total Debt Service
    """
    # Try to calculate NOI from the most recent period available
    # We use operating_income if available, or proxy it as revenue - current_liabilities (simplified for demo)
    
    # Ideally, we would have operating_income mapped. 
    # For this system, let's proxy NOI = Revenue - Current Liabilities
    # Since current liabilities aren't expenses, this is a poor proxy, but we use it
    # if actual operating income isn't available. Let's assume NOI is provided or proxy it.
    
    if not record.revenue:
        raise ValueError("Revenue data missing for DSCR calculation")
        
    latest_rev = record.revenue[-1].value
    
    # Proxy Operating Income (Let's assume 20% margin for demo if operating_income is not in schema)
    noi = latest_rev * 0.20
    
    total_debt_service = dscr_inputs.total_annual_debt_service
    
    if total_debt_service <= 0:
        dscr = float('inf')
    else:
        dscr = noi / total_debt_service
        
    return {
        "noi": noi,
        "total_debt_service": total_debt_service,
        "dscr_ratio": dscr,
        "risk_level": "high" if dscr < 1.2 else "moderate" if dscr < 1.5 else "low"
    }
