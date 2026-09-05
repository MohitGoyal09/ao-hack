"""Domain language shared by the covenant workflow.

The models intentionally distinguish a machine-produced *draft status* from an
officer-signed certificate.  That distinction is a safety invariant throughout
the backend, not a label added by the frontend.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class DraftStatus(StrEnum):
    COMPLIANT = "DRAFT_COMPLIANT"
    BREACH = "DRAFT_BREACH"
    REVIEW = "NEEDS_REVIEW"


class ReviewerDecision(StrEnum):
    PENDING = "pending"
    APPROVE_ADDBACK = "approve_addback"
    REJECT_ADDBACK = "reject_addback"


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

