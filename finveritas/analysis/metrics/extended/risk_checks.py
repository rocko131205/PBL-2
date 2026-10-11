"""Advisory risk checks (ported from DeterminX ``metrics/risk.py``).

These return ``RiskIndicator`` objects and are stored OUTSIDE the main fact
ledger, deliberately: ``risk.build_risk_dashboard`` turns every ledger signal into
an input of the overall risk level, so feeding these in would silently move the
credit verdict of analyses that already exist. They are a second, advisory lens
shown in the "Risk & alerts" section.

Weak current ratio, weak interest coverage and weak DSCR are intentionally NOT
repeated here: the existing ledger already carries those signals.
"""
from __future__ import annotations

from typing import List

from finveritas.shared.schema import CheckStatus, NormalizedCompanyRecord, RiskIndicator

from . import _util as u

_PASS, _WARN, _FAIL = CheckStatus.PASS, CheckStatus.WARN, CheckStatus.FAIL
CATEGORY = "advisory"


def _ind(name: str, status: CheckStatus, detail: str, threshold: str, value=None) -> RiskIndicator:
    return RiskIndicator(name=name, category=CATEGORY, status=status, value=value, threshold=threshold,
                         detail=detail, severity_weight=1.0)


def _skip(name: str, why: str, threshold: str) -> RiskIndicator:
    return RiskIndicator(name=name, category=CATEGORY, status=CheckStatus.SKIP, threshold=threshold,
                         detail=why, severity_weight=1.0)


def compute_advisory_risks(record: NormalizedCompanyRecord) -> List[RiskIndicator]:
    out: List[RiskIndicator] = []

    # Negative EBITDA (reported, or operating income + depreciation)
    ebitda = u.series(record, "ebitda")
    if not ebitda:
        oi, dep = u.series(record, "operating_income"), u.series(record, "depreciation")
        ebitda = {p: oi[p] + dep[p] for p in set(oi) & set(dep)}
    thr = "FAIL if latest EBITDA < 0"
    if ebitda:
        p, v = u.latest_point(ebitda)
        out.append(_ind("Negative EBITDA", _FAIL if v < 0 else _PASS,
                        f"EBITDA in {p} = {v:,.2f}" + (" (negative)" if v < 0 else ""), thr, v))
    else:
        out.append(_skip("Negative EBITDA", "Needs EBITDA, or operating income plus depreciation.", thr))

    # Declining PAT
    thr = "FAIL if latest PAT < 0 or it fell in >= 66% of periods; WARN if >= 50%"
    ni_p = u.common_periods(record, ["net_income"])
    if len(ni_p) >= 2:
        vals = u.aligned(record, "net_income", ni_p)
        declines = sum(1 for i in range(1, len(vals)) if vals[i] < vals[i - 1])
        share = declines / (len(vals) - 1)
        status = _FAIL if vals[-1] < 0 or share >= 0.66 else _WARN if share >= 0.5 else _PASS
        out.append(_ind("Declining profit (PAT)", status,
                        f"PAT fell in {declines} of {len(vals) - 1} year-on-year comparisons; latest PAT = {vals[-1]:,.2f}",
                        thr, vals[-1]))
    else:
        out.append(_skip("Declining profit (PAT)", "Needs at least 2 periods of net income.", thr))

    # Margin compression
    thr = "FAIL if net margin fell >= 5pp end to end; WARN if it fell at all"
    nm_p = u.common_periods(record, ["revenue", "net_income"])
    margins = [n / r * 100 for n, r in zip(u.aligned(record, "net_income", nm_p), u.aligned(record, "revenue", nm_p)) if r]
    if len(nm_p) >= 2 and len(margins) >= 2:
        delta = margins[-1] - margins[0]
        status = _FAIL if delta <= -5 else _WARN if delta < 0 else _PASS
        out.append(_ind("Margin compression", status,
                        f"Net margin moved from {margins[0]:.2f}% to {margins[-1]:.2f}% ({delta:+.2f}pp) across the periods",
                        thr, delta))
    else:
        out.append(_skip("Margin compression", "Needs at least 2 periods with revenue and net income.", thr))

    # Rising debt
    thr = "FAIL if total-debt CAGR > 25%; WARN if > 10%"
    d_p = u.common_periods(record, ["total_debt"])
    if len(d_p) >= 2:
        vals = u.aligned(record, "total_debt", d_p)
        g = u.cagr_pct(vals[0], vals[-1], len(vals) - 1)
        if g is None:
            out.append(_skip("Rising debt", "Debt growth can't be computed from a non-positive value.", thr))
        else:
            out.append(_ind("Rising debt", _FAIL if g > 25 else _WARN if g > 10 else _PASS,
                            f"Total debt CAGR = {g:.2f}% across the periods", thr, g))
    else:
        out.append(_skip("Rising debt", "Needs at least 2 periods of total debt.", thr))

    # Negative operating cash flow
    thr = "FAIL if latest operating cash flow < 0"
    ocf = u.series(record, "operating_cash_flow")
    if ocf:
        p, v = u.latest_point(ocf)
        out.append(_ind("Negative operating cash flow", _FAIL if v < 0 else _PASS,
                        f"Operating cash flow in {p} = {v:,.2f}", thr, v))
    else:
        out.append(_skip("Negative operating cash flow", "Needs operating cash flow.", thr))

    # Receivables growing faster than revenue
    thr = "FAIL if receivables CAGR exceeds revenue CAGR by > 20pp; WARN if > 10pp"
    p_ar = u.common_periods(record, ["accounts_receivable", "revenue"])
    if len(p_ar) >= 2:
        ar, rv = u.aligned(record, "accounts_receivable", p_ar), u.aligned(record, "revenue", p_ar)
        ag, rg = u.cagr_pct(ar[0], ar[-1], len(ar) - 1), u.cagr_pct(rv[0], rv[-1], len(rv) - 1)
        if ag is None or rg is None:
            out.append(_skip("Receivables outpacing revenue", "Growth can't be computed from a non-positive value.", thr))
        else:
            gap = ag - rg
            out.append(_ind("Receivables outpacing revenue", _FAIL if gap > 20 else _WARN if gap > 10 else _PASS,
                            f"Receivables CAGR {ag:.2f}% vs revenue CAGR {rg:.2f}% (gap {gap:+.2f}pp)", thr, gap))
    else:
        out.append(_skip("Receivables outpacing revenue", "Needs receivables and revenue for 2+ periods.", thr))
    return out
