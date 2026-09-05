"""Typed covenant calculation and safe-abstention policy for the demo workflow.

Extraction may propose a rule or mapping; only this typed calculator and review gate
produce the displayed draft status. It never evaluates model-generated code.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class DraftStatus(StrEnum):
    COMPLIANT = "DRAFT_COMPLIANT"
    BREACH = "DRAFT_BREACH"
    REVIEW = "NEEDS_REVIEW"


class Citation(BaseModel):
    document: str
    locator: str
    excerpt: str


class Fact(BaseModel):
    key: str
    label: str
    amount: float
    unit: str = "USD millions"
    evidence: str
    cited: bool = True


class DemoCase(BaseModel):
    id: str
    name: str
    narrative: str
    agreement: str
    agreement_version: str
    test_date: str
    covenant_name: str
    formula_label: str
    numerator_keys: list[str]
    subtract_keys: list[str] = Field(default_factory=list)
    denominator_keys: list[str]
    threshold: float
    comparator: Literal["<=", ">="]
    citations: list[Citation]
    facts: list[Fact]
    required_evidence: list[str] = Field(default_factory=list)
    amendment_note: str | None = None
    original_threshold: float | None = None
    risk_note: str | None = None


class RunRequest(BaseModel):
    reviewer_decision: Literal["pending", "approve_addback", "reject_addback"] = "pending"
    reviewer_name: str | None = None


def cite(document: str, locator: str, excerpt: str) -> Citation:
    return Citation(document=document, locator=locator, excerpt=excerpt)


COMMON_FACTS = [
    Fact(key="funded_debt", label="Funded debt", amount=1200, evidence="Q2 debt schedule, row 12"),
    Fact(key="operating_leases", label="Operating lease liabilities", amount=260, evidence="Q2 lease schedule, row 5"),
    Fact(key="unrestricted_cash", label="Unrestricted cash", amount=100, evidence="Q2 balance sheet, cash note"),
    Fact(key="ebitda", label="Consolidated EBITDA", amount=350, evidence="Q2 management accounts, EBITDA bridge"),
]

DEMO_CASES: dict[str, DemoCase] = {
    "aurora-net-leverage": DemoCase(
        id="aurora-net-leverage", name="Aurora: net leverage passes",
        narrative="Same company and Q2 financials as Beacon. Aurora permits unrestricted cash netting and excludes operating leases.",
        agreement="Aurora Credit Agreement", agreement_version="Original agreement", test_date="2026-06-30",
        covenant_name="Maximum Total Net Leverage Ratio",
        formula_label="(Funded debt − unrestricted cash) ÷ Consolidated EBITDA",
        numerator_keys=["funded_debt"], subtract_keys=["unrestricted_cash"], denominator_keys=["ebitda"], threshold=3.5, comparator="<=", facts=COMMON_FACTS,
        citations=[
            cite("Aurora Credit Agreement", "§6.11(a), p. 84", "Total Net Leverage Ratio shall not exceed 3.50 to 1.00."),
            cite("Aurora Credit Agreement", "§1.01, p. 41", "Funded Debt excludes operating lease liabilities; unrestricted cash may reduce debt."),
        ], risk_note="Contract-specific lease and cash definitions drive this result.",
    ),
    "beacon-gross-leverage": DemoCase(
        id="beacon-gross-leverage", name="Beacon: gross leverage breaches",
        narrative="The same company and financials fail because Beacon includes operating leases and does not permit cash netting.",
        agreement="Beacon Term Loan Agreement", agreement_version="Original agreement", test_date="2026-06-30",
        covenant_name="Maximum Consolidated Leverage Ratio",
        formula_label="(Funded debt + operating lease liabilities) ÷ Consolidated EBITDA",
        numerator_keys=["funded_debt", "operating_leases"], denominator_keys=["ebitda"], threshold=4.0, comparator="<=", facts=COMMON_FACTS,
        citations=[
            cite("Beacon Term Loan Agreement", "§7.10(a), p. 92", "Consolidated Leverage Ratio shall not exceed 4.00 to 1.00."),
            cite("Beacon Term Loan Agreement", "§1.01, p. 49", "Debt includes lease obligations. No cash netting is permitted."),
        ], risk_note="This is the deliberately opposite verdict: 4.17x is above the 4.00x limit.",
    ),
    "beacon-amendment": DemoCase(
        id="beacon-amendment", name="Beacon: amendment controls",
        narrative="The same leverage is compliant only because Amendment No. 2 replaced the original threshold for this test period.",
        agreement="Beacon Term Loan Agreement", agreement_version="Amendment No. 2 (controlling)", test_date="2026-06-30",
        covenant_name="Maximum Consolidated Leverage Ratio",
        formula_label="(Funded debt + operating lease liabilities) ÷ Consolidated EBITDA",
        numerator_keys=["funded_debt", "operating_leases"], denominator_keys=["ebitda"], threshold=4.25, original_threshold=4.0, comparator="<=", facts=COMMON_FACTS,
        citations=[
            cite("Beacon Amendment No. 2", "§2, p. 3", "For the quarter ending June 30, 2026, the threshold is 4.25 to 1.00."),
            cite("Beacon Term Loan Agreement", "§7.10(a), p. 92", "Original threshold was 4.00 to 1.00."),
        ], amendment_note="Amendment No. 2 controls this specific quarter; the original 4.00x term is superseded.",
    ),
    "meridian-evidence-gap": DemoCase(
        id="meridian-evidence-gap", name="Meridian: evidence gap requires review",
        narrative="A proposed EBITDA add-back improves the ratio, but its management support is missing. The system must not issue a compliant conclusion.",
        agreement="Meridian Revolving Credit Agreement", agreement_version="Amendment No. 1", test_date="2026-06-30",
        covenant_name="Maximum Net Leverage Ratio",
        formula_label="(Funded debt − unrestricted cash) ÷ (EBITDA + approved restructuring add-back)",
        numerator_keys=["funded_debt"], subtract_keys=["unrestricted_cash"], denominator_keys=["ebitda", "restructuring_addback"], threshold=3.5, comparator="<=",
        facts=[
            Fact(key="funded_debt", label="Funded debt", amount=1200, evidence="Q2 debt schedule, row 12"),
            Fact(key="unrestricted_cash", label="Unrestricted cash", amount=100, evidence="Q2 balance sheet, cash note"),
            Fact(key="ebitda", label="Consolidated EBITDA", amount=270, evidence="Q2 management accounts, EBITDA bridge"),
            Fact(key="restructuring_addback", label="Proposed restructuring add-back", amount=80, evidence="Management schedule requested; not attached", cited=False),
        ], required_evidence=["Management schedule supporting the $80m restructuring add-back"],
        citations=[
            cite("Meridian Revolving Credit Agreement", "§1.01, p. 38", "Restructuring charges may be added back only when supported by a certificate of an authorized officer."),
            cite("Meridian Revolving Credit Agreement", "§6.12, p. 77", "Maximum Net Leverage Ratio shall not exceed 3.50 to 1.00."),
        ], risk_note="A candidate 3.14x result is displayed, but the conclusion is held pending evidence and reviewer decision.",
    ),
}


def case_summary(case: DemoCase) -> dict:
    return {"id": case.id, "name": case.name, "narrative": case.narrative, "agreement": case.agreement, "agreement_version": case.agreement_version, "test_date": case.test_date, "scenario_type": "evidence_gap" if case.required_evidence else "amendment" if case.amendment_note else "comparison"}


def amount(case: DemoCase, keys: list[str], decision: str) -> float:
    facts = {fact.key: fact.amount for fact in case.facts}
    if "restructuring_addback" in keys and decision == "reject_addback":
        return sum(facts[key] for key in keys if key != "restructuring_addback")
    return sum(facts[key] for key in keys)


def run_case(case: DemoCase, request: RunRequest) -> dict:
    numerator = amount(case, case.numerator_keys, request.reviewer_decision) - amount(case, case.subtract_keys, request.reviewer_decision)
    denominator = amount(case, case.denominator_keys, request.reviewer_decision)
    ratio = round(numerator / denominator, 2)
    passes = ratio <= case.threshold if case.comparator == "<=" else ratio >= case.threshold
    evidence_gap = bool(case.required_evidence) and request.reviewer_decision == "pending"
    if evidence_gap:
        status, reason = DraftStatus.REVIEW, "Required add-back evidence is missing. Candidate arithmetic is not a certifiable conclusion."
    elif passes:
        status, reason = DraftStatus.COMPLIANT, "All listed evidence is present and deterministic calculation satisfies the controlling threshold."
    else:
        status, reason = DraftStatus.BREACH, "All listed evidence is present and deterministic calculation fails the controlling threshold."
    headroom = round(case.threshold - ratio, 2) if case.comparator == "<=" else round(ratio - case.threshold, 2)
    now = datetime.now(UTC).isoformat()
    evidence = [{"type": "fact", "label": fact.label, "value": f"${fact.amount:,.0f}m", "source": fact.evidence, "supported": fact.cited} for fact in case.facts]
    reviewer_event = ({"step": "6", "label": "Reviewer decision recorded", "detail": f"{request.reviewer_decision} by {request.reviewer_name or 'Demo reviewer'}"} if request.reviewer_decision != "pending" else None)
    return {
        "case": case_summary(case), "status": status, "status_reason": reason,
        "calculation": {"formula": case.formula_label, "numerator": round(numerator, 2), "denominator": round(denominator, 2), "ratio": ratio, "threshold": case.threshold, "comparator": case.comparator, "headroom": headroom, "unit": "x", "original_threshold": case.original_threshold},
        "citations": [citation.model_dump() for citation in case.citations], "evidence": evidence,
        "blocking_issues": case.required_evidence if evidence_gap else [],
        "trace": [
            {"step": "1", "label": "Resolved controlling agreement", "detail": case.agreement_version},
            {"step": "2", "label": "Compiled cited covenant rule", "detail": case.covenant_name},
            {"step": "3", "label": "Mapped financial evidence", "detail": f"{len(case.facts)} source facts"},
            {"step": "4", "label": "Calculated deterministically", "detail": f"{ratio:.2f}x vs {case.threshold:.2f}x"},
            {"step": "5", "label": "Applied review policy", "detail": reason},
            *([reviewer_event] if reviewer_event else []),
        ],
        "certificate": {"title": "Draft Compliance Certificate", "draft_mark": "DRAFT — AUTHORIZED OFFICER REVIEW REQUIRED", "agreement": case.agreement, "agreement_version": case.agreement_version, "test_date": case.test_date, "result": status, "finalization_allowed": status != DraftStatus.REVIEW, "generated_at": now},
    }
