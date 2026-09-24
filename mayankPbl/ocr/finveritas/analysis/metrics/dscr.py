"""DSCR Engine — Methodology-Aware Debt Service Coverage Ratio Calculator

V2 REPLACEMENT: The V1 engine used `noi = revenue * 0.20` (a hardcoded proxy).
This is fundamentally wrong — DSCR must use ACTUAL operating income, not a
fabricated percentage of revenue.

DSCR = Net Operating Income / Total Annual Debt Service

Numerator hierarchy (use best available):
  1. EBITDA                        — most conservative proxy for cash flow
  2. Operating Income (EBIT)       — pre-interest, pre-tax operating earnings
  3. Net Income + Interest + Dep + Tax — reconstructed operating income
  4. INSUFFICIENT DATA             — explicitly stated, never fabricated

Denominator:
  - Existing debt principal repayment + interest (user-provided)
  - Proposed debt principal repayment + interest (user-provided or calculated)
  - Must include ALL debt service obligations

If the user provides loan amount + tenure + rate but not annual payments,
the engine calculates annualized debt service from those parameters.

Design constraints:
  - Pure deterministic computation.
  - Full methodology documentation in every result.
  - Never fabricate missing inputs — explicitly state what's missing.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from finveritas.shared.schema import (
    CheckStatus,
    DSCRInputs,
    DSCRMethodology,
    DSCRResult,
    FactLedgerEntry,
    FactStatus,
    NormalizedCompanyRecord,
    RiskLevel,
)


def _calculate_annual_payment(
    principal: float,
    annual_rate_pct: float,
    tenure_years: float,
    structure: str = "equal_installment",
) -> float:
    """Calculate annual debt service (principal + interest) from loan terms.

    Supports:
      - equal_installment: standard amortizing loan (PMT formula)
      - bullet: interest-only during tenure, principal at maturity
    """
    if principal <= 0 or tenure_years <= 0:
        return 0.0

    r = annual_rate_pct / 100.0

    if structure == "bullet":
        # Interest-only payments; principal repaid at maturity
        # Annualize the bullet: principal / tenure + interest
        annual_interest = principal * r
        annual_principal = principal / tenure_years  # amortized for DSCR purposes
        return annual_principal + annual_interest

    # Default: equal_installment (standard amortizing loan)
    if r < 1e-9:
        # Zero interest rate
        return principal / tenure_years

    monthly_rate = r / 12.0
    n_months = int(tenure_years * 12)
    if n_months <= 0:
        return principal

    # PMT formula: M = P * [r(1+r)^n] / [(1+r)^n - 1]
    monthly_payment = principal * (monthly_rate * (1 + monthly_rate) ** n_months) / (
        (1 + monthly_rate) ** n_months - 1
    )
    return monthly_payment * 12  # annualize


def _resolve_numerator(record: NormalizedCompanyRecord) -> tuple[Optional[float], str, str, List[str]]:
    """Determine the best available numerator for DSCR.

    Returns: (value, name, formula, inputs_used)

    Hierarchy:
      1. EBITDA
      2. Operating Income
      3. Reconstructed: Net Income + Interest + Depreciation + Tax
      4. None (insufficient data)
    """
    # Option 1: EBITDA
    ebitda = record.latest_value("ebitda")
    if ebitda is not None:
        return ebitda, "EBITDA", "EBITDA (from financial data)", ["ebitda"]

    # Option 2: Operating Income (EBIT)
    oi = record.latest_value("operating_income")
    if oi is not None:
        return oi, "Operating Income (EBIT)", "Operating Income (from financial data)", ["operating_income"]

    # Try net_operating_income as a mapped fallback
    noi = record.latest_value("net_operating_income")
    if noi is not None:
        return noi, "Net Operating Income", "Net Operating Income (from financial data)", ["net_operating_income"]

    # Option 3: Reconstruct from components
    ni = record.latest_value("net_income")
    ie = record.latest_value("interest_expense")
    dep = record.latest_value("depreciation")
    tax = record.latest_value("income_tax")

    if ni is not None and ie is not None:
        # At minimum: Net Income + Interest Expense
        reconstructed = ni + abs(ie)
        formula_parts = ["Net Income", "Interest Expense"]
        inputs = ["net_income", "interest_expense"]

        if dep is not None:
            reconstructed += abs(dep)
            formula_parts.append("Depreciation")
            inputs.append("depreciation")

        if tax is not None:
            reconstructed += abs(tax)
            formula_parts.append("Tax Provision")
            inputs.append("income_tax")

        formula = " + ".join(formula_parts) + " (reconstructed)"
        return reconstructed, "Reconstructed Operating Income", formula, inputs

    # Option 4: Insufficient data
    return None, "INSUFFICIENT_DATA", "Unable to determine — no EBITDA, Operating Income, or sufficient components", []


def _resolve_denominator(dscr_inputs: DSCRInputs) -> tuple[float, List[str], List[str]]:
    """Resolve the total annual debt service from user inputs.

    Returns: (total_debt_service, components_list, assumptions_list)
    """
    components: List[str] = []
    assumptions: List[str] = []
    total = 0.0

    # Existing debt service
    if dscr_inputs.total_existing_debt_service > 0:
        total += dscr_inputs.total_existing_debt_service
        components.append(
            f"Existing debt service: {dscr_inputs.existing_loan_principal_repayment:,.0f} principal + "
            f"{dscr_inputs.existing_loan_interest:,.0f} interest = "
            f"{dscr_inputs.total_existing_debt_service:,.0f}"
        )

    # Proposed debt service
    proposed = dscr_inputs.total_proposed_debt_service
    if proposed > 0:
        total += proposed
        components.append(
            f"Proposed debt service: {dscr_inputs.proposed_loan_principal_repayment:,.0f} principal + "
            f"{dscr_inputs.proposed_loan_interest:,.0f} interest = {proposed:,.0f}"
        )
    elif (dscr_inputs.proposed_loan_amount and dscr_inputs.proposed_loan_amount > 0
          and dscr_inputs.proposed_tenure_years and dscr_inputs.proposed_tenure_years > 0
          and dscr_inputs.proposed_interest_rate is not None):
        # Calculate from loan terms
        structure = dscr_inputs.repayment_structure or "equal_installment"
        annual_payment = _calculate_annual_payment(
            principal=dscr_inputs.proposed_loan_amount,
            annual_rate_pct=dscr_inputs.proposed_interest_rate,
            tenure_years=dscr_inputs.proposed_tenure_years,
            structure=structure,
        )
        total += annual_payment
        components.append(
            f"Proposed debt service (calculated): {annual_payment:,.0f}/year "
            f"({structure} on {dscr_inputs.proposed_loan_amount:,.0f} @ "
            f"{dscr_inputs.proposed_interest_rate}% for {dscr_inputs.proposed_tenure_years}yr)"
        )
        assumptions.append(
            f"Proposed debt service calculated as {structure} from loan terms "
            f"({dscr_inputs.proposed_loan_amount:,.0f}, {dscr_inputs.proposed_interest_rate}%, "
            f"{dscr_inputs.proposed_tenure_years}yr)"
        )

    return total, components, assumptions


def compute_dscr(
    record: NormalizedCompanyRecord,
    dscr_inputs: DSCRInputs,
) -> DSCRResult:
    """Compute DSCR with full methodology documentation.

    This is the core DSCR calculation that replaces the V1 hardcoded proxy.

    Returns a DSCRResult with:
      - The computed ratio (or None if insufficient data)
      - Full methodology documentation
      - Risk classification
      - Interpretation context
    """
    # Resolve numerator
    noi_value, noi_name, noi_formula, noi_inputs = _resolve_numerator(record)

    # Resolve denominator
    total_ds, ds_components, ds_assumptions = _resolve_denominator(dscr_inputs)

    # Build assumptions list
    assumptions: List[str] = list(ds_assumptions)
    limitations: List[str] = []

    # Determine period
    period = None
    for field_name in ["ebitda", "operating_income", "net_operating_income", "net_income"]:
        series = getattr(record, field_name, [])
        if series:
            period = sorted(series, key=lambda x: x.period)[-1].period
            break

    # Check if we can calculate
    if noi_value is None:
        return DSCRResult(
            numerator_value=0.0,
            denominator_value=total_ds,
            dscr_ratio=None,
            risk_level=RiskLevel.INSUFFICIENT_DATA,
            methodology=DSCRMethodology(
                numerator_name=noi_name,
                numerator_formula=noi_formula,
                numerator_source="unavailable",
                denominator_components=ds_components,
                time_period=period or "N/A",
                assumptions=assumptions,
                limitations=[
                    "DSCR cannot be computed: no operating income, EBITDA, or sufficient "
                    "component data available. Required: at minimum, Operating Income or "
                    "EBITDA from financial statements.",
                ],
                data_quality_notes="Numerator data unavailable — DSCR is not calculable",
            ),
            interpretation=(
                "DSCR cannot be calculated due to insufficient financial data. "
                "The system requires at minimum EBITDA or Operating Income to compute "
                "a meaningful debt service coverage ratio. This does NOT mean the company "
                "cannot service debt — it means the available data is insufficient to "
                "make that determination."
            ),
        )

    if total_ds <= 0:
        # No debt service to cover
        limitations.append("No debt service obligations provided — DSCR is formally undefined")
        return DSCRResult(
            numerator_value=noi_value,
            denominator_value=0.0,
            dscr_ratio=None,
            risk_level=RiskLevel.INSUFFICIENT_DATA,
            methodology=DSCRMethodology(
                numerator_name=noi_name,
                numerator_formula=noi_formula,
                numerator_source=record.source_provenance.get(noi_inputs[0], record.source) if noi_inputs else record.source,
                denominator_components=["No debt service obligations provided"],
                time_period=period or "N/A",
                assumptions=assumptions,
                limitations=limitations,
            ),
            interpretation=(
                f"Operating income ({noi_name}) is {noi_value:,.0f}, but no debt service "
                "obligations were provided. To calculate DSCR, please provide either: "
                "(a) existing loan repayment details, or (b) proposed loan terms "
                "(amount, tenure, interest rate)."
            ),
        )

    # Compute DSCR
    dscr = noi_value / total_ds

    # Risk classification
    if dscr >= 2.0:
        risk = RiskLevel.LOW
    elif dscr >= 1.5:
        risk = RiskLevel.MODERATE
    elif dscr >= 1.0:
        risk = RiskLevel.HIGH
    else:
        risk = RiskLevel.CRITICAL

    # Add methodology notes
    if noi_name != "EBITDA":
        limitations.append(
            f"EBITDA was not available; {noi_name} was used instead. "
            "DSCR based on EBITDA is generally preferred as it better "
            "approximates cash flow available for debt service."
        )

    # Build interpretation
    interpretation_parts = [
        f"DSCR of {dscr:.2f}x indicates the company's {noi_name.lower()} "
        f"({noi_value:,.0f}) covers annual debt service ({total_ds:,.0f}) "
        f"{dscr:.2f} times."
    ]
    if dscr >= 2.0:
        interpretation_parts.append(
            "This is generally considered strong debt coverage. "
            "The company has substantial margin to service existing and proposed debt."
        )
    elif dscr >= 1.5:
        interpretation_parts.append(
            "This is adequate but not exceptional coverage. "
            "The company can service debt but has limited margin for unexpected revenue declines."
        )
    elif dscr >= 1.0:
        interpretation_parts.append(
            "This is marginal coverage. The company can technically service debt "
            "but has very little buffer. Any revenue decline could impair debt service."
        )
    else:
        interpretation_parts.append(
            "DSCR below 1.0 indicates the company's operating income is INSUFFICIENT "
            "to cover debt service. This represents a significant credit risk."
        )

    return DSCRResult(
        numerator_value=noi_value,
        denominator_value=total_ds,
        dscr_ratio=round(dscr, 4),
        risk_level=risk,
        methodology=DSCRMethodology(
            numerator_name=noi_name,
            numerator_formula=noi_formula,
            numerator_source=record.source_provenance.get(noi_inputs[0], record.source) if noi_inputs else record.source,
            denominator_components=ds_components,
            time_period=period or "N/A",
            assumptions=assumptions,
            limitations=limitations,
            data_quality_notes=None,
        ),
        interpretation=" ".join(interpretation_parts),
    )


def dscr_to_fact_entry(result: DSCRResult) -> FactLedgerEntry:
    """Convert a DSCRResult to a FactLedgerEntry for the fact ledger."""
    risk_map = {
        RiskLevel.LOW: CheckStatus.PASS,
        RiskLevel.MODERATE: CheckStatus.PASS,
        RiskLevel.HIGH: CheckStatus.WARN,
        RiskLevel.CRITICAL: CheckStatus.FAIL,
        RiskLevel.INSUFFICIENT_DATA: None,
    }

    return FactLedgerEntry(
        metric="dscr",
        display_name="Debt Service Coverage Ratio (DSCR)",
        category="debt_service",
        value=result.dscr_ratio,
        unit="ratio",
        period=result.methodology.time_period,
        formula=f"DSCR = {result.methodology.numerator_name} / Total Annual Debt Service",
        inputs_used=[result.methodology.numerator_name, "debt_service_obligations"],
        status=FactStatus.VALID if result.dscr_ratio is not None else FactStatus.INSUFFICIENT_DATA,
        risk_signal=risk_map.get(result.risk_level),
        risk_detail=result.interpretation,
        notes="; ".join(result.methodology.limitations) if result.methodology.limitations else None,
    )
