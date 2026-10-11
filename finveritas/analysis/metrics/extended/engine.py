"""Builds the extended fact ledger.

Mirrors DeterminX's ``build_fact_ledger``: every category module runs inside its
own try/except, so a bug in one degrades to a single INSUFFICIENT_DATA entry for
that category instead of taking the others down.

The result is a separate ``FinancialFactLedger`` from the core one. Same schema,
no overlapping metric names (one source of truth per number), but kept apart so
the existing risk dashboard, scorecard and LLM prompts are unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List, Tuple

from finveritas.shared.schema import (
    FactLedgerEntry,
    FactStatus,
    FinancialFactLedger,
    NormalizedCompanyRecord,
)

from .cash_flow import compute_cash_flow
from .cost import compute_cost
from .credit import compute_credit
from .domain import compute_domain
from .efficiency import compute_efficiency, compute_returns
from .growth import compute_growth, compute_revenue, compute_trends

_MODULES: List[Tuple[str, Callable[[NormalizedCompanyRecord], List[FactLedgerEntry]]]] = [
    ("revenue", compute_revenue),
    ("cost", compute_cost),
    ("efficiency", compute_efficiency),
    ("returns", compute_returns),
    ("cash_flow", compute_cash_flow),
    ("growth", compute_growth),
    ("trend", compute_trends),
    ("credit", compute_credit),
    ("domain", compute_domain),
]

_USABLE = (FactStatus.VALID, FactStatus.ESTIMATED)


def build_extended_ledger(record: NormalizedCompanyRecord) -> Tuple[FinancialFactLedger, List[str]]:
    """Run every extended module. Returns (ledger, errors)."""
    entries: List[FactLedgerEntry] = []
    errors: List[str] = []
    for category, fn in _MODULES:
        try:
            entries.extend(fn(record))
        except Exception as exc:  # one category must never take the rest down
            errors.append(f"{category}: {exc}")
            entries.append(FactLedgerEntry(
                metric=f"{category}_module", display_name=f"{category.title()} metrics", category=category,
                value=None, status=FactStatus.INSUFFICIENT_DATA, notes=f"Could not be computed ({type(exc).__name__}).",
            ))
    ledger = FinancialFactLedger(
        entity_id=record.entity_id,
        analysis_timestamp=datetime.now(timezone.utc).isoformat(),
        currency=record.currency,
        entries=entries,
    )
    return ledger, errors


def status_summary(ledger: FinancialFactLedger) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for e in ledger.entries:
        summary[e.status.value] = summary.get(e.status.value, 0) + 1
    return summary


def coverage_pct(ledger: FinancialFactLedger) -> float:
    """Share of entries that hold a usable number (VALID or ESTIMATED)."""
    if not ledger.entries:
        return 0.0
    ok = sum(1 for e in ledger.entries if e.status in _USABLE and e.value is not None)
    return round(ok / len(ledger.entries) * 100, 1)
