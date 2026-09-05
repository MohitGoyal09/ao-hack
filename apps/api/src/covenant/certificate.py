"""Versioned draft-certificate renderer."""

from __future__ import annotations

from datetime import UTC, datetime

from .domain import CalculationResult, CovenantCase, DraftCertificate, DraftStatus, EvidenceItem
from .hashing import short_hash, stable_hash


class CertificateRenderer:
    def render(
        self,
        case: CovenantCase,
        status: DraftStatus,
        calculation: CalculationResult,
        evidence: list[EvidenceItem],
        generated_at: datetime | None = None,
    ) -> DraftCertificate:
        generated_at = generated_at or datetime.now(UTC)
        manifest_hash = stable_hash(evidence)
        identity = {
            "case": case.id,
            "rule": case.rule.id,
            "test_date": case.test_date,
            "status": status,
            "calculation": calculation,
            "manifest": manifest_hash,
        }
        return DraftCertificate(
            id=f"cert-{short_hash(identity)}",
            agreement=case.agreement,
            agreement_version=case.agreement_version,
            test_date=case.test_date,
            covenant_name=case.rule.name,
            result=status,
            ratio=calculation.ratio,
            threshold=calculation.threshold,
            evidence_manifest_hash=manifest_hash,
            # Human sign-off is outside this demo. This only means the draft is
            # complete enough to enter the officer-approval step.
            finalization_allowed=status != DraftStatus.REVIEW,
            generated_at=generated_at,
        )
