"""Evidence manifest assembly at the rule/fact seam."""

from __future__ import annotations

from .domain import CovenantCase, EvidenceItem, ReviewerDecision, RunRequest
from .hashing import stable_hash


def assemble_evidence(case: CovenantCase, command: RunRequest) -> list[EvidenceItem]:
    evidence = [
        EvidenceItem(
            type="fact",
            label=fact.label,
            value=f"${fact.amount:,.0f}m",
            source=fact.source,
            locator=fact.source_locator,
            supported=(
                fact.supported
                or (
                    fact.requires_review
                    and command.reviewer_decision == ReviewerDecision.APPROVE_ADDBACK
                )
            ),
            source_hash=fact.source_hash,
        )
        for fact in case.facts
    ]
    evidence.extend(
        EvidenceItem(
            type="clause",
            label=f"{citation.document} {citation.locator}",
            value=citation.excerpt,
            source=citation.document,
            locator=citation.locator,
            supported=True,
            source_hash=citation.document_hash,
        )
        for citation in case.rule.citations
    )
    if command.reviewer_decision != ReviewerDecision.PENDING:
        decision = {
            "decision": command.reviewer_decision,
            "reviewer": command.reviewer_name,
            "rationale": command.reviewer_rationale,
        }
        evidence.append(
            EvidenceItem(
                type="decision",
                label="Recorded adjustment decision",
                value=command.reviewer_decision.value,
                source=command.reviewer_name or "Unnamed reviewer",
                locator="workflow review gate",
                supported=bool(command.reviewer_name),
                source_hash=stable_hash(decision),
            )
        )
    return evidence
