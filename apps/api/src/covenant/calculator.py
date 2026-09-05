"""Allow-listed covenant arithmetic.

The calculator accepts typed rules and facts only.  It never evaluates source
text, Python expressions, or model output as executable code.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .domain import (
    CalculationLine,
    CalculationResult,
    CovenantCase,
    ReviewerDecision,
    ReviewIssue,
)


TWO_PLACES = Decimal("0.01")


def _rounded(value: Decimal) -> float:
    return float(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


class CovenantCalculator:
    """Evaluate one contract-compiled rule against its financial fact set."""

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
