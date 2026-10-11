"""Narration of the working-capital credit assessment (Tandon Method II).

The numbers come from ``metrics.extended.credit``; this only explains them. The narrator is told
MPBF is an estimate and Drawing Power cannot be computed, so it says so rather than implying a
bank-sanctioned limit.
"""
from __future__ import annotations

from typing import Any, Dict, List

from finveritas.intelligence.narrate import narrate
from finveritas.shared.schema import FactLedgerEntry

_ROLE = (
    "You explain a working-capital assessment. 'Estimated MPBF' is an internal estimate from the balance sheet "
    "alone, not a bank-sanctioned limit, and 'Estimated Drawing Power' cannot be computed without a bank sanction "
    "letter and stock/receivables ageing. State both caveats plainly. Write 4-6 concise, professional sentences."
)


def run(entries: List[FactLedgerEntry], currency: str | None) -> Dict[str, Any]:
    credit = [e for e in entries if e.category == "credit"]
    facts = [{
        "metric": e.display_name, "value": e.value, "unit": e.unit, "period": e.period, "status": e.status.value,
        "note": e.notes,
    } for e in credit]
    if not any(e.value is not None for e in credit):
        return {"status": "UNAVAILABLE", "reason": "Not enough balance-sheet data for a working-capital assessment.",
                "narrative": None}
    return {"status": "OK", "narrative": narrate(
        _ROLE, {"currency": currency, "facts": facts},
        "Explain the working-capital position and what the estimate can and cannot be used for.")}
