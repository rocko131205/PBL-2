"""Advanced debt-service analysis (V3).

This is the "credit committee" view of debt serviceability, layered on top of the
existing single-number DSCR engine (which stays as the simple baseline).

What it adds:
  1. Selectable numerator (cash available for debt service):
       - EBITDA        : earnings proxy, ignores taxes/capex (most optimistic)
       - EBIT          : operating income
       - OCF           : operating cash flow + interest added back
       - CFADS         : OCF + interest - capex  (most conservative, real cash)
  2. A full year-by-year amortization schedule (equal-installment / bullet / balloon,
     optional moratorium), not a single blended payment.
  3. DSCR computed for EVERY year of the loan -> minimum and average DSCR.
     The MINIMUM year is what a lender underwrites against.
  4. Stress testing: revenue haircuts and interest-rate shocks -> min DSCR under stress.
  5. Companion coverage ratios (interest coverage, Debt/EBITDA).

All pure deterministic math. No LLM. Every number is reproducible.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .schema import NormalizedCompanyRecord, RiskLevel


# -------------------------------------------------------------------------
# Inputs & result models
# -------------------------------------------------------------------------

class LoanTerms(BaseModel):
    principal: float = Field(..., description="Loan amount")
    annual_rate_pct: float = Field(..., description="Annual interest rate, percent")
    tenure_years: int = Field(..., ge=1, description="Loan tenure in whole years")
    structure: str = Field("equal_installment", description="equal_installment | bullet | balloon")
    moratorium_years: int = Field(0, ge=0, description="Interest-only grace years before principal repayment")
    balloon_fraction: float = Field(0.0, ge=0.0, le=1.0, description="For 'balloon': fraction repaid at maturity")
    existing_annual_debt_service: float = Field(0.0, description="Existing debt service to add to each year")


class AmortRow(BaseModel):
    year: int
    opening_balance: float
    principal: float
    interest: float
    total_payment: float
    closing_balance: float


class StressResult(BaseModel):
    scenario: str
    description: str
    min_dscr: Optional[float]
    delta_vs_base: Optional[float] = Field(None, description="min_dscr - base min_dscr")
    breaches_1x: bool = Field(False, description="True if min DSCR falls below 1.0")


class DSCRScheduleResult(BaseModel):
    numerator_basis: str
    numerator_value: Optional[float]
    numerator_formula: str
    schedule: List[AmortRow] = Field(default_factory=list)
    dscr_by_year: List[Optional[float]] = Field(default_factory=list)
    min_dscr: Optional[float] = None
    avg_dscr: Optional[float] = None
    min_dscr_year: Optional[int] = None
    risk_level: RiskLevel = RiskLevel.INSUFFICIENT_DATA
    interest_coverage: Optional[float] = None
    debt_to_ebitda: Optional[float] = None
    stress_results: List[StressResult] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


# -------------------------------------------------------------------------
# Amortization
# -------------------------------------------------------------------------

def build_amortization_schedule(terms: LoanTerms) -> List[AmortRow]:
    """Year-by-year principal + interest for the loan.

    Structures:
      - equal_installment: level annual payment (annual amortization)
      - bullet: interest-only every year, full principal at maturity
      - balloon: amortize (1 - balloon_fraction) over tenure, balloon_fraction at maturity
    Moratorium years pay interest only, principal starts afterwards.
    """
    P = float(terms.principal)
    r = terms.annual_rate_pct / 100.0
    n = int(terms.tenure_years)
    if P <= 0 or n <= 0:
        return []

    mora = min(terms.moratorium_years, n)
    amort_years = max(n - mora, 1)
    rows: List[AmortRow] = []
    balance = P

    if terms.structure == "bullet":
        for y in range(1, n + 1):
            interest = balance * r
            principal = balance if y == n else 0.0
            rows.append(AmortRow(year=y, opening_balance=balance, principal=principal,
                                 interest=interest, total_payment=principal + interest,
                                 closing_balance=balance - principal))
            balance -= principal
        return rows

    if terms.structure == "balloon":
        balloon = P * terms.balloon_fraction
        amortizing_principal = P - balloon
        per_year_principal = amortizing_principal / amort_years
        for y in range(1, n + 1):
            interest = balance * r
            if y <= mora:
                principal = 0.0
            else:
                principal = per_year_principal
                if y == n:
                    principal += balloon  # repay balloon at maturity
            principal = min(principal, balance)
            rows.append(AmortRow(year=y, opening_balance=balance, principal=principal,
                                 interest=interest, total_payment=principal + interest,
                                 closing_balance=balance - principal))
            balance -= principal
        return rows

    # equal_installment (level annual payment over the amortizing years)
    if r < 1e-9:
        level_payment = P / amort_years
    else:
        level_payment = P * (r * (1 + r) ** amort_years) / ((1 + r) ** amort_years - 1)

    for y in range(1, n + 1):
        interest = balance * r
        if y <= mora:
            principal = 0.0
            payment = interest
        else:
            principal = level_payment - interest
            principal = min(max(principal, 0.0), balance)
            payment = principal + interest
        rows.append(AmortRow(year=y, opening_balance=balance, principal=principal,
                             interest=interest, total_payment=payment,
                             closing_balance=balance - principal))
        balance -= principal
    return rows


# -------------------------------------------------------------------------
# Numerator (cash available for debt service)
# -------------------------------------------------------------------------

def resolve_numerator(record: NormalizedCompanyRecord, basis: str) -> tuple[Optional[float], str]:
    """Return (value, formula) for the chosen cash-available basis.

    basis: 'ebitda' | 'ebit' | 'ocf' | 'cfads'
    """
    ebitda = record.latest_value("ebitda")
    ebit = record.latest_value("operating_income")
    ocf = record.latest_value("operating_cash_flow")
    interest = record.latest_value("interest_expense")
    capex = record.latest_value("capital_expenditure")

    if basis == "ebitda":
        return ebitda, "EBITDA"
    if basis == "ebit":
        return ebit, "Operating Income (EBIT)"
    if basis == "ocf":
        if ocf is None:
            return None, "Operating Cash Flow + Interest (unavailable)"
        val = ocf + (abs(interest) if interest is not None else 0.0)
        return val, "Operating Cash Flow + Interest add-back"
    if basis == "cfads":
        if ocf is None:
            return None, "CFADS (Operating Cash Flow unavailable)"
        val = ocf + (abs(interest) if interest is not None else 0.0) - (abs(capex) if capex is not None else 0.0)
        return val, "OCF + Interest - CapEx (CFADS)"
    return None, f"unknown basis '{basis}'"


def _classify(min_dscr: Optional[float]) -> RiskLevel:
    if min_dscr is None:
        return RiskLevel.INSUFFICIENT_DATA
    if min_dscr >= 2.0:
        return RiskLevel.LOW
    if min_dscr >= 1.5:
        return RiskLevel.MODERATE
    if min_dscr >= 1.0:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


# -------------------------------------------------------------------------
# Main computation
# -------------------------------------------------------------------------

def compute_dscr_schedule(
    record: NormalizedCompanyRecord,
    terms: LoanTerms,
    basis: str = "cfads",
    run_stress: bool = True,
) -> DSCRScheduleResult:
    """Compute a full year-by-year DSCR schedule with stress tests.

    The numerator (annual cash available) is held constant across years — a
    deliberately conservative assumption absent a forecast (see Phase 5 forecasting).
    """
    numerator, formula = resolve_numerator(record, basis)
    notes: List[str] = []

    # Fall back through bases if the preferred one is unavailable.
    if numerator is None:
        for fb in ("cfads", "ocf", "ebitda", "ebit"):
            if fb == basis:
                continue
            numerator, formula = resolve_numerator(record, fb)
            if numerator is not None:
                notes.append(f"Requested basis '{basis}' unavailable; used '{fb}' instead.")
                basis = fb
                break

    schedule = build_amortization_schedule(terms)

    result = DSCRScheduleResult(
        numerator_basis=basis,
        numerator_value=round(numerator, 2) if numerator is not None else None,
        numerator_formula=formula,
        schedule=schedule,
        notes=notes,
    )

    # Coverage companions
    ebit = record.latest_value("operating_income")
    interest = record.latest_value("interest_expense")
    ebitda = record.latest_value("ebitda")
    total_debt = record.latest_value("total_debt") or record.latest_value("total_liabilities")
    if ebit is not None and interest is not None and abs(interest) > 1e-9:
        result.interest_coverage = round(ebit / abs(interest), 2)
    if total_debt is not None and ebitda is not None and abs(ebitda) > 1e-9:
        result.debt_to_ebitda = round(total_debt / ebitda, 2)

    if numerator is None or not schedule:
        notes.append("DSCR schedule not computable: missing cash-flow numerator or loan terms.")
        return result

    dscr_by_year: List[Optional[float]] = []
    for row in schedule:
        service = row.total_payment + terms.existing_annual_debt_service
        dscr_by_year.append(round(numerator / service, 3) if service > 1e-9 else None)

    valid = [d for d in dscr_by_year if d is not None]
    result.dscr_by_year = dscr_by_year
    if valid:
        result.min_dscr = min(valid)
        result.avg_dscr = round(sum(valid) / len(valid), 3)
        result.min_dscr_year = dscr_by_year.index(result.min_dscr) + 1
        result.risk_level = _classify(result.min_dscr)

    if run_stress and valid:
        result.stress_results = _run_stress(record, terms, basis, numerator, result.min_dscr)

    return result


def _min_dscr_for(numerator: float, terms: LoanTerms) -> Optional[float]:
    schedule = build_amortization_schedule(terms)
    vals = []
    for row in schedule:
        service = row.total_payment + terms.existing_annual_debt_service
        if service > 1e-9:
            vals.append(numerator / service)
    return round(min(vals), 3) if vals else None


def _run_stress(
    record: NormalizedCompanyRecord,
    terms: LoanTerms,
    basis: str,
    base_numerator: float,
    base_min: Optional[float],
) -> List[StressResult]:
    """Revenue haircuts (scale the numerator) and rate shocks (rebuild schedule)."""
    results: List[StressResult] = []

    for haircut in (0.10, 0.20, 0.30):
        stressed_num = base_numerator * (1 - haircut)
        m = _min_dscr_for(stressed_num, terms)
        results.append(StressResult(
            scenario=f"revenue_-{int(haircut*100)}pct",
            description=f"Earnings/cash fall {int(haircut*100)}%",
            min_dscr=m,
            delta_vs_base=round(m - base_min, 3) if (m is not None and base_min is not None) else None,
            breaches_1x=(m is not None and m < 1.0),
        ))

    for bump in (1.0, 2.0, 3.0):
        shocked = terms.model_copy(update={"annual_rate_pct": terms.annual_rate_pct + bump})
        m = _min_dscr_for(base_numerator, shocked)
        results.append(StressResult(
            scenario=f"rate_+{int(bump*100)}bps",
            description=f"Interest rate rises {int(bump*100)} bps",
            min_dscr=m,
            delta_vs_base=round(m - base_min, 3) if (m is not None and base_min is not None) else None,
            breaches_1x=(m is not None and m < 1.0),
        ))

    return results
