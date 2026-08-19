from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

# -------------------------------------------------------------------------
# Core Financial Schemas
# -------------------------------------------------------------------------

class FinancialPeriod(BaseModel):
    period: str = Field(..., description="e.g. 2023-FY, 2024-Q1")
    value: float = Field(..., description="The financial value for this period")

class NormalizedCompanyRecord(BaseModel):
    """
    Standardized internal representation of a company, regardless of source
    (Bloomberg PDF, Ticker, or CSV).
    """
    entity_id: str = Field(..., description="Company name or ticker symbol")
    source: str = Field(..., description="E.g., bloomberg_pdf, ticker, csv, user_input")
    currency: Optional[str] = Field(None, description="Currency code, e.g., USD, INR")
    
    # Standard Financials
    revenue: List[FinancialPeriod] = Field(default_factory=list)
    net_operating_income: List[FinancialPeriod] = Field(default_factory=list)
    total_assets: List[FinancialPeriod] = Field(default_factory=list)
    total_liabilities: List[FinancialPeriod] = Field(default_factory=list)
    current_assets: List[FinancialPeriod] = Field(default_factory=list)
    current_liabilities: List[FinancialPeriod] = Field(default_factory=list)
    equity: List[FinancialPeriod] = Field(default_factory=list)
    
    # SaaS-specific or Derived Info
    saas_metrics: Dict[str, Any] = Field(default_factory=dict, description="e.g. ARR, CAC, NRR")
    qualitative_context: Optional[str] = Field(None, description="Extracted management commentary or notes")

# -------------------------------------------------------------------------
# Agent Workflow State Schemas
# -------------------------------------------------------------------------

class DSCRInputs(BaseModel):
    """Inputs required for calculating Debt Service Coverage Ratio."""
    existing_loan_principal_repayment: float = Field(0.0, description="Annual principal repayment on existing debt")
    existing_loan_interest: float = Field(0.0, description="Annual interest on existing debt")
    proposed_loan_principal_repayment: float = Field(0.0, description="Proposed new annual principal repayment")
    proposed_loan_interest: float = Field(0.0, description="Proposed new annual interest")
    
    @property
    def total_annual_debt_service(self) -> float:
        return (self.existing_loan_principal_repayment + self.existing_loan_interest + 
                self.proposed_loan_principal_repayment + self.proposed_loan_interest)

class PeerCompany(BaseModel):
    entity_id: str
    saas_subtype: str
    revenue_scale: str
    rule_of_40: Optional[float] = None
    
class CreditRiskReport(BaseModel):
    entity_id: str
    dscr_ratio: Optional[float] = None
    saas_subtype: str
    peer_comparison_summary: str
    qualitative_summary: str
    major_strengths: List[str] = Field(default_factory=list)
    major_risks: List[str] = Field(default_factory=list)
    risk_classification: str = Field(..., description="LOW, MEDIUM, HIGH")
    narrative: str = Field(..., description="Final explainable recommendation")
