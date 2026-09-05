"""Evidence completeness and human-review policy."""

from __future__ import annotations

from .domain import (
    CalculationResult,
    CovenantAssessment,
    CovenantCase,
    CovenantResultStatus,
    CoverageReport,
    CoverageStatus,
    DraftStatus,
    ReviewerDecision,
    ReviewIssue,
    RunRequest,
)


class ReviewPolicy:
    """Fail closed when evidence, authority, or document precedence is unclear."""

    def assess(
        self,
        case: CovenantCase,
        calculation: CalculationResult,
        command: RunRequest,
        calculation_issues: list[ReviewIssue],
    ) -> tuple[DraftStatus, str, list[ReviewIssue]]:
        issues = list(calculation_issues)
        controlling = [document for document in case.documents if document.controlling]
        if len(controlling) != 1:
            issues.append(
                ReviewIssue(
                    code="DOCUMENT_PRECEDENCE_UNRESOLVED",
                    severity="blocking",
                    message="Exactly one controlling agreement version is required.",
                )
            )

        if not case.rule.active:
            issues.append(
                ReviewIssue(
                    code="COVENANT_NOT_ACTIVE",
                    severity="blocking",
                    message="The selected covenant is not active for this test period.",
                )
            )

        if not case.rule.citations:
            issues.append(
                ReviewIssue(
                    code="RULE_WITHOUT_CITATION",
                    severity="blocking",
                    message="The compiled covenant rule has no supporting clause citation.",
                )
            )

        unsupported = [fact for fact in case.facts if not fact.supported]
        unresolved = [fact for fact in unsupported if fact.requires_review]
        unsupported_without_resolution_path = [
            fact for fact in unsupported if not fact.requires_review
        ]
        if unsupported_without_resolution_path:
            issues.append(
                ReviewIssue(
                    code="SOURCE_EVIDENCE_MISSING",
                    severity="blocking",
                    message="One or more financial inputs have no supporting evidence.",
                    related_keys=[fact.key for fact in unsupported_without_resolution_path],
                )
            )
        if unresolved and command.reviewer_decision == ReviewerDecision.PENDING:
            issues.append(
                ReviewIssue(
                    code="ADJUSTMENT_EVIDENCE_REQUIRED",
                    severity="blocking",
                    message=(
                        "Supporting evidence and an authorized decision are required for "
                        + ", ".join(fact.label for fact in unresolved)
                        + "."
                    ),
                    related_keys=[fact.key for fact in unresolved],
                )
            )

        if command.reviewer_decision != ReviewerDecision.PENDING and not command.reviewer_name:
            issues.append(
                ReviewIssue(
                    code="REVIEWER_IDENTITY_REQUIRED",
                    severity="blocking",
                    message="A named reviewer is required to record an adjustment decision.",
                )
            )
        if (
            command.reviewer_decision != ReviewerDecision.PENDING
            and not command.reviewer_rationale
        ):
            issues.append(
                ReviewIssue(
                    code="REVIEWER_RATIONALE_REQUIRED",
                    severity="blocking",
                    message="Reviewer rationale is required for an adjustment decision.",
                )
            )

        blockers = [issue for issue in issues if issue.severity == "blocking"]
        if blockers:
            return (
                DraftStatus.REVIEW,
                blockers[0].message,
                issues,
            )

        if calculation.passed is True:
            return (
                DraftStatus.COMPLIANT,
                "Declared supported scope passes deterministic arithmetic; not full agreement compliance.",
                issues,
            )
        if calculation.passed is False:
            return (
                DraftStatus.BREACH,
                "Complete listed evidence and deterministic arithmetic fail the controlling threshold.",
                issues,
            )
        return (
            DraftStatus.REVIEW,
            "The calculation did not produce a decisionable ratio.",
            issues,
        )

    def assess_full(
        self,
        case: CovenantCase,
        calculation: CalculationResult,
        assessments: list[CovenantAssessment],
        coverage: CoverageReport,
        command: RunRequest,
        calculation_issues: list[ReviewIssue],
    ) -> tuple[DraftStatus, str, list[ReviewIssue]]:
        """Fail-closed verdict over the full rule checklist.

        Preserve computed failures even if another covenant is indeterminate;
        an empty evaluated set can never pass.
        """
        status, reason, issues = self.assess(case, calculation, command, calculation_issues)
        if any(a.status == CovenantResultStatus.FAIL for a in assessments):
            if status != DraftStatus.BREACH:
                # A supported-rule failure survives indeterminate siblings,
                # but evidence/policy blockers still hold the draft in review.
                if any(i.severity == "blocking" for i in issues):
                    return DraftStatus.REVIEW, (
                        "A supported covenant fails on deterministic arithmetic, "
                        "but blocking evidence/policy issues require review first: "
                        + reason
                    ), issues
                failed = [a for a in assessments if a.status == CovenantResultStatus.FAIL]
                return DraftStatus.BREACH, (
                    "Complete listed evidence and deterministic arithmetic fail "
                    f"the controlling threshold ({failed[0].detail})."
                ), issues
            return status, reason, issues
        evaluated = [
            a for a in assessments
            if a.status in (CovenantResultStatus.PASS, CovenantResultStatus.FAIL)
        ]
        if not evaluated:
            issues = list(issues) + [ReviewIssue(
                code="NO_EVALUATED_COVENANTS",
                severity="blocking",
                message="Empty set of evaluated covenants cannot pass.",
            )]
            return DraftStatus.REVIEW, "Empty set of evaluated covenants cannot pass.", issues
        if any(a.status == CovenantResultStatus.INDETERMINATE for a in assessments):
            return DraftStatus.REVIEW, (
                reason + " Coverage: " + coverage.note
            ), issues
        if coverage.status == CoverageStatus.INCOMPLETE and status == DraftStatus.COMPLIANT:
            reason = reason + " Coverage: " + coverage.note
        return status, reason, issues
