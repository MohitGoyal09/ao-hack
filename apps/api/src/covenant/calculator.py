"""Allow-listed covenant arithmetic.

The calculator accepts typed rules and facts only.  It never evaluates source
text, Python expressions, or model output as executable code.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .domain import (
    CalculationLine,
    CalculationResult,
    CovenantAssessment,
    CovenantCase,
    CovenantResultStatus,
    CovenantRule,
    CoverageReport,
    CoverageStatus,
    ReviewerDecision,
    ReviewIssue,
)


TWO_PLACES = Decimal("0.01")


def _rounded(value: Decimal) -> float:
    return float(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


class CovenantCalculator:
    """Evaluate one contract-compiled rule against its financial fact set."""

    def evaluate_all(
        self, case: CovenantCase, decision: ReviewerDecision
    ) -> tuple[list[CovenantAssessment], CoverageReport, list[ReviewIssue]]:
        """Run the FULL applicable rule list; unsupported items are flagged, never omitted."""
        assessments: list[CovenantAssessment] = []
        issues: list[ReviewIssue] = []
        assessed: list[str] = []
        excluded: list[str] = list(case.unsupported_obligations)
        for rule in case.all_rules():
            if not rule.supported:
                assessments.append(
                    CovenantAssessment(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        status=CovenantResultStatus.UNSUPPORTED,
                        detail=rule.unsupported_reason
                        or "Calculation not supported in v1.",
                    )
                )
                excluded.append(f"{rule.name} ({rule.id}): unsupported")
                continue
            if not rule.active:
                assessments.append(
                    CovenantAssessment(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        status=CovenantResultStatus.NOT_APPLICABLE,
                        detail="Rule is not active for this test period.",
                    )
                )
                excluded.append(f"{rule.name} ({rule.id}): not applicable this period")
                continue
            single_case = case.model_copy(update={"rule": rule})
            calculation, rule_issues = self.calculate(single_case, decision)
            issues.extend(rule_issues)
            blocking_for_rule = [
                i
                for i in rule_issues
                if i.severity == "blocking"
                and i.code in ("MISSING_FINANCIAL_FACT", "ZERO_DENOMINATOR")
            ]
            if calculation.passed is True:
                assessments.append(
                    CovenantAssessment(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        status=CovenantResultStatus.PASS,
                        detail=(
                            f"Ratio {calculation.ratio:.2f}x satisfies "
                            f"{calculation.comparator} {calculation.threshold:.2f}x "
                            "for the declared supported scope only; "
                            "not full agreement compliance."
                        ),
                        ratio=calculation.ratio,
                        threshold=calculation.threshold,
                        passed=True,
                    )
                )
            elif calculation.passed is False:
                assessments.append(
                    CovenantAssessment(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        status=CovenantResultStatus.FAIL,
                        detail=(
                            f"Ratio {calculation.ratio:.2f}x breaches "
                            f"{calculation.comparator} {calculation.threshold:.2f}x."
                        ),
                        ratio=calculation.ratio,
                        threshold=calculation.threshold,
                        passed=False,
                    )
                )
            else:
                assessments.append(
                    CovenantAssessment(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        status=CovenantResultStatus.INDETERMINATE,
                        detail="; ".join(i.message for i in blocking_for_rule)
                        or "No decisionable ratio.",
                        ratio=calculation.ratio,
                        threshold=calculation.threshold,
                        passed=None,
                    )
                )
            assessed.append(f"{rule.name} ({rule.id})")
        evaluated = [
            a
            for a in assessments
            if a.status in (CovenantResultStatus.PASS, CovenantResultStatus.FAIL)
        ]
        if not evaluated:
            coverage_status = CoverageStatus.INCOMPLETE
            note = "Empty set of evaluated covenants cannot pass."
        elif excluded:
            coverage_status = CoverageStatus.INCOMPLETE
            note = (
                "Declared supported scope assessed; "
                f"{len(excluded)} obligation(s) excluded — see excluded list."
            )
        else:
            coverage_status = CoverageStatus.COMPLETE
            note = "All declared obligations assessed."
        return assessments, CoverageReport(
            status=coverage_status, assessed=assessed, excluded=excluded, note=note
        ), issues

    def calculate(
        self, case: CovenantCase, decision: ReviewerDecision
    ) -> tuple[CalculationResult, list[ReviewIssue]]:
        facts = {fact.key: fact for fact in case.facts}
        issues: list[ReviewIssue] = []
        lines: list[CalculationLine] = []

        required_keys = {
            *case.rule.numerator_keys,
            *case.rule.subtract_keys,
            *case.rule.denominator_keys,
        }
        missing_keys = sorted(required_keys - facts.keys())
        if missing_keys:
            issues.append(
                ReviewIssue(
                    code="MISSING_FINANCIAL_FACT",
                    severity="blocking",
                    message="Required financial facts are absent from the case package.",
                    related_keys=missing_keys,
                )
            )

        def included(fact_key: str) -> bool:
            fact = facts.get(fact_key)
            if not fact:
                return False
            if fact.requires_review and decision == ReviewerDecision.REJECT_ADDBACK:
                return False
            return True

        def total(keys: list[str], operation: str) -> Decimal:
            value = Decimal("0")
            for key in keys:
                fact = facts.get(key)
                if not fact:
                    continue
                use_fact = included(key)
                if use_fact:
                    value += Decimal(str(fact.amount))
                lines.append(
                    CalculationLine(
                        operation=operation,
                        fact_key=key,
                        label=fact.label,
                        amount=fact.amount,
                        included=use_fact,
                        reason=(
                            "Included by the compiled agreement rule"
                            if use_fact
                            else "Excluded by recorded reviewer decision"
                        ),
                    )
                )
            return value

        numerator = total(case.rule.numerator_keys, "add")
        numerator -= total(case.rule.subtract_keys, "subtract")
        denominator = total(case.rule.denominator_keys, "add")

        if denominator == 0:
            issues.append(
                ReviewIssue(
                    code="ZERO_DENOMINATOR",
                    severity="blocking",
                    message="The covenant denominator is zero; no ratio can be issued.",
                )
            )
            ratio = None
            passed = None
            headroom = None
        else:
            raw_ratio = numerator / denominator
            ratio = _rounded(raw_ratio)
            threshold = Decimal(str(case.rule.threshold))
            passed = (
                raw_ratio <= threshold
                if case.rule.comparator == "<="
                else raw_ratio >= threshold
            )
            raw_headroom = (
                threshold - raw_ratio
                if case.rule.comparator == "<="
                else raw_ratio - threshold
            )
            headroom = _rounded(raw_headroom)

        return (
            CalculationResult(
                formula=case.rule.formula_label,
                numerator=_rounded(numerator),
                denominator=_rounded(denominator),
                ratio=ratio,
                threshold=case.rule.threshold,
                comparator=case.rule.comparator,
                headroom=headroom,
                original_threshold=case.rule.original_threshold,
                passed=passed,
                lines=lines,
            ),
            issues,
        )
