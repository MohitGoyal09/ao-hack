"""Domain language shared by the covenant workflow.

The models intentionally distinguish a machine-produced *draft status* from an
officer-signed certificate.  That distinction is a safety invariant throughout
the backend, not a label added by the frontend.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_serializer


TWO_PLACES = Decimal("0.01")


def money_str(value: float | int) -> str:
    """Render a financial value as an exact two-decimal string.

    The internal pipeline stores money as floats already rounded to two places
    (see calculator.py).  JSON per the implementation contract carries these as
    exact decimal strings, never binary floats, so a borrower can rely on the
    wire value matching the ledger exactly.
    """
    return str(Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


class DraftStatus(StrEnum):
    COMPLIANT = "DRAFT_COMPLIANT"
    BREACH = "DRAFT_BREACH"
    REVIEW = "NEEDS_REVIEW"


class ReviewerDecision(StrEnum):
    PENDING = "pending"
    APPROVE_ADDBACK = "approve_addback"
    REJECT_ADDBACK = "reject_addback"


class CovenantResultStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INDETERMINATE = "indeterminate"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class CoverageStatus(StrEnum):
    COMPLETE = "complete_for_declared_scope"
    INCOMPLETE = "incomplete"


class CovenantAssessment(BaseModel):
    rule_id: str
    rule_name: str
    status: CovenantResultStatus
    detail: str
    ratio: float | None = None
    threshold: float | None = None
    passed: bool | None = None

    @field_serializer("ratio", "threshold")
    def _serialize_optional_money(self, value: float | None, _info) -> str | None:
        return None if value is None else money_str(value)


class CoverageReport(BaseModel):
    status: CoverageStatus
    assessed: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    note: str = ""


class Citation(BaseModel):
    document_id: str
    document: str
    locator: str
    excerpt: str
    document_hash: str


class DocumentVersion(BaseModel):
    id: str
    title: str
    kind: Literal["agreement", "amendment", "waiver", "certificate_form"]
    effective_date: str
    supersedes: list[str] = Field(default_factory=list)
    controlling: bool = False


class FinancialFact(BaseModel):
    key: str
    label: str
    amount: float
    unit: str = "USD millions"
    period: str
    source: str
    source_locator: str
    source_hash: str
    supported: bool = True
    requires_review: bool = False

    @field_serializer("amount")
    def _serialize_amount(self, value: float, _info) -> str:
        return money_str(value)


class CovenantRule(BaseModel):
    id: str
    name: str
    formula_label: str
    numerator_keys: list[str]
    subtract_keys: list[str] = Field(default_factory=list)
    denominator_keys: list[str]
    threshold: float
    comparator: Literal["<=", ">="]
    measurement_period: str
    citations: list[Citation]
    active: bool = True
    original_threshold: float | None = None
    supported: bool = True
    unsupported_reason: str | None = None

    @field_serializer("threshold")
    def _serialize_threshold(self, value: float, _info) -> str:
        return money_str(value)

    @field_serializer("original_threshold")
    def _serialize_original_threshold(self, value: float | None, _info) -> str | None:
        return None if value is None else money_str(value)


class CovenantCase(BaseModel):
    id: str
    name: str
    narrative: str
    agreement: str
    agreement_version: str
    test_date: str
    scenario_type: Literal["comparison", "amendment", "evidence_gap"]
    documents: list[DocumentVersion]
    rule: CovenantRule
    facts: list[FinancialFact]
    amendment_note: str | None = None
    risk_note: str | None = None
    extra_rules: list[CovenantRule] = Field(default_factory=list)
    unsupported_obligations: list[str] = Field(default_factory=list)

    def all_rules(self) -> list[CovenantRule]:
        return [self.rule, *self.extra_rules]


class RunRequest(BaseModel):
    reviewer_decision: ReviewerDecision = ReviewerDecision.PENDING
    reviewer_name: str | None = None
    reviewer_rationale: str | None = None


class CalculationLine(BaseModel):
    operation: Literal["add", "subtract"]
    fact_key: str
    label: str
    amount: float
    included: bool
    reason: str

    @field_serializer("amount")
    def _serialize_amount(self, value: float, _info) -> str:
        return money_str(value)


class CalculationResult(BaseModel):
    formula: str
    numerator: float
    denominator: float
    ratio: float | None
    threshold: float
    comparator: str
    headroom: float | None
    unit: str = "x"
    original_threshold: float | None = None
    passed: bool | None
    lines: list[CalculationLine]

    @field_serializer("numerator", "denominator", "threshold", "headroom")
    def _serialize_money(self, value: float | None, _info) -> str | None:
        return None if value is None else money_str(value)

    @field_serializer("ratio")
    def _serialize_ratio(self, value: float | None, _info) -> str | None:
        return None if value is None else money_str(value)

    @field_serializer("original_threshold")
    def _serialize_original_threshold(self, value: float | None, _info) -> str | None:
        return None if value is None else money_str(value)


class ReviewIssue(BaseModel):
    code: str
    severity: Literal["blocking", "warning"]
    message: str
    related_keys: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    type: Literal["fact", "clause", "decision"]
    label: str
    value: str
    source: str
    locator: str
    supported: bool
    source_hash: str


class AuditEvent(BaseModel):
    sequence: int
    step: str
    label: str
    detail: str
    artifact_hash: str
    created_at: datetime


class DraftCertificate(BaseModel):
    id: str
    title: str = "Draft Compliance Certificate"
    draft_mark: str = "DRAFT — AUTHORIZED OFFICER REVIEW REQUIRED"
    agreement: str
    agreement_version: str
    test_date: str
    covenant_name: str
    result: DraftStatus
    ratio: float | None
    threshold: float
    evidence_manifest_hash: str
    finalization_allowed: bool
    generated_at: datetime

    @field_serializer("ratio")
    def _serialize_ratio(self, value: float | None, _info) -> str | None:
        return None if value is None else money_str(value)

    @field_serializer("threshold")
    def _serialize_threshold(self, value: float, _info) -> str:
        return money_str(value)


class WorkflowResult(BaseModel):
    run_id: str
    case: dict[str, str]
    status: DraftStatus
    status_reason: str
    calculation: CalculationResult
    citations: list[Citation]
    evidence: list[EvidenceItem]
    blocking_issues: list[str]
    review_issues: list[ReviewIssue]
    trace: list[AuditEvent]
    certificate: DraftCertificate
    covenant_results: list[CovenantAssessment] = Field(default_factory=list)
    coverage: CoverageReport | None = None

