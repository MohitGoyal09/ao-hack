"""Curated, auditable cases used by the local hackathon demonstration.

The Aurora, Beacon, and Meridian numbers and agreement names are synthetic so
the UI cannot accidentally imply that a public borrower has received a legal
conclusion.  The shapes mirror the primary-source covenant patterns documented
in ``docs/``.

One case (``aon-term-loan-leverage``) is compiled from real SEC-filed source
documents by :mod:`.ingestion` and flows through the identical calculator,
policy, and audit path.  Its narrative and risk note state the financial-period
and definition proxies so a demo result cannot be mistaken for a certification
verdict.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Literal

from .domain import Citation, CovenantCase, CovenantRule, DocumentVersion, FinancialFact
from .hashing import stable_hash
from .ingestion import AON_CASE_ID, AON_TEST_DATE, build_aon_term_loan_case


PERIOD = "Trailing twelve months ended 2026-06-30"

INTEREST_COVERAGE_UNSUPPORTED = (
    "Interest coverage ratio — out of scope for v1; detected but not calculated."
)


def _document(
    document_id: str,
    title: str,
    kind: Literal["agreement", "amendment", "waiver", "certificate_form"],
    effective_date: str,
    *,
    controlling: bool = False,
    supersedes: list[str] | None = None,
) -> DocumentVersion:
    return DocumentVersion(
        id=document_id,
        title=title,
        kind=kind,
        effective_date=effective_date,
        controlling=controlling,
        supersedes=supersedes or [],
    )


def _citation(document_id: str, document: str, locator: str, excerpt: str) -> Citation:
    return Citation(
        document_id=document_id,
        document=document,
        locator=locator,
        excerpt=excerpt,
        document_hash=stable_hash({"id": document_id, "title": document}),
    )


def _fact(
    key: str,
    label: str,
    amount: float,
    source: str,
    locator: str,
    *,
    supported: bool = True,
    requires_review: bool = False,
) -> FinancialFact:
    return FinancialFact(
        key=key,
        label=label,
        amount=amount,
        period=PERIOD,
        source=source,
        source_locator=locator,
        source_hash=stable_hash(
            {"source": source, "locator": locator, "amount": amount, "period": PERIOD}
        ),
        supported=supported,
        requires_review=requires_review,
    )


COMMON_FACTS = [
    _fact("funded_debt", "Funded debt", 1200, "Q2 debt schedule", "row 12"),
    _fact(
        "operating_leases",
        "Operating lease liabilities",
        260,
        "Q2 lease schedule",
        "row 5",
    ),
    _fact(
        "unrestricted_cash",
        "Unrestricted cash",
        100,
        "Q2 balance sheet",
        "cash and equivalents note",
    ),
    _fact(
        "ebitda",
        "Consolidated EBITDA",
        350,
        "Q2 management accounts",
        "EBITDA bridge",
    ),
]


def build_demo_catalog() -> dict[str, CovenantCase]:
    cases = [
        CovenantCase(
            id="aurora-net-leverage",
            name="Aurora: net leverage passes",
            narrative=(
                "Same company and Q2 financials as Beacon. Aurora permits unrestricted "
                "cash netting and excludes operating leases."
            ),
            agreement="Aurora Credit Agreement",
            agreement_version="Original agreement",
            test_date="2026-06-30",
            scenario_type="comparison",
            documents=[
                _document(
                    "aurora-original",
                    "Aurora Credit Agreement",
                    "agreement",
                    "2025-01-15",
                    controlling=True,
                )
            ],
            rule=CovenantRule(
                id="aurora-max-net-leverage",
                name="Maximum Total Net Leverage Ratio",
                formula_label="(Funded debt − unrestricted cash) ÷ Consolidated EBITDA",
                numerator_keys=["funded_debt"],
                subtract_keys=["unrestricted_cash"],
                denominator_keys=["ebitda"],
                threshold=3.5,
                comparator="<=",
                measurement_period=PERIOD,
                citations=[
                    _citation(
                        "aurora-original",
                        "Aurora Credit Agreement",
                        "§6.11(a), p. 84",
                        "Total Net Leverage Ratio shall not exceed 3.50 to 1.00.",
                    ),
                    _citation(
                        "aurora-original",
                        "Aurora Credit Agreement",
                        "§1.01, p. 41",
                        "Funded Debt excludes operating leases; unrestricted cash may reduce debt.",
                    ),
                ],
            ),
            facts=deepcopy(COMMON_FACTS),
            risk_note="Contract-specific lease and cash definitions drive this result.",
            unsupported_obligations=[INTEREST_COVERAGE_UNSUPPORTED],
        ),
        CovenantCase(
            id="beacon-gross-leverage",
            name="Beacon: gross leverage breaches",
            narrative=(
                "The same company and financials fail because Beacon includes operating "
                "leases and does not permit cash netting."
            ),
            agreement="Beacon Term Loan Agreement",
            agreement_version="Original agreement",
            test_date="2026-06-30",
            scenario_type="comparison",
            documents=[
                _document(
                    "beacon-original",
                    "Beacon Term Loan Agreement",
                    "agreement",
                    "2025-02-28",
                    controlling=True,
                )
            ],
            rule=CovenantRule(
                id="beacon-max-gross-leverage",
                name="Maximum Consolidated Leverage Ratio",
                formula_label=(
                    "(Funded debt + operating lease liabilities) ÷ Consolidated EBITDA"
                ),
                numerator_keys=["funded_debt", "operating_leases"],
                denominator_keys=["ebitda"],
                threshold=4.0,
                comparator="<=",
                measurement_period=PERIOD,
                citations=[
                    _citation(
                        "beacon-original",
                        "Beacon Term Loan Agreement",
                        "§7.10(a), p. 92",
                        "Consolidated Leverage Ratio shall not exceed 4.00 to 1.00.",
                    ),
                    _citation(
                        "beacon-original",
                        "Beacon Term Loan Agreement",
                        "§1.01, p. 49",
                        "Debt includes lease obligations. No cash netting is permitted.",
                    ),
                ],
            ),
            facts=deepcopy(COMMON_FACTS),
            risk_note="The agreement-defined 4.17x result exceeds the 4.00x limit.",
            unsupported_obligations=[INTEREST_COVERAGE_UNSUPPORTED],
        ),
        CovenantCase(
            id="beacon-amendment",
            name="Beacon: amendment controls",
            narrative=(
                "The same leverage is compliant only because Amendment No. 2 replaced "
                "the original threshold for this test period."
            ),
            agreement="Beacon Term Loan Agreement",
            agreement_version="Amendment No. 2 (controlling)",
            test_date="2026-06-30",
            scenario_type="amendment",
            documents=[
                _document(
                    "beacon-original",
                    "Beacon Term Loan Agreement",
                    "agreement",
                    "2025-02-28",
                ),
                _document(
                    "beacon-amendment-2",
                    "Beacon Amendment No. 2",
                    "amendment",
                    "2026-04-01",
                    controlling=True,
                    supersedes=["beacon-original:§7.10(a)"],
                ),
            ],
            rule=CovenantRule(
                id="beacon-amended-max-leverage",
                name="Maximum Consolidated Leverage Ratio",
                formula_label=(
                    "(Funded debt + operating lease liabilities) ÷ Consolidated EBITDA"
                ),
                numerator_keys=["funded_debt", "operating_leases"],
                denominator_keys=["ebitda"],
                threshold=4.25,
                original_threshold=4.0,
                comparator="<=",
                measurement_period=PERIOD,
                citations=[
                    _citation(
                        "beacon-amendment-2",
                        "Beacon Amendment No. 2",
                        "§2, p. 3",
                        "For the quarter ending June 30, 2026, the threshold is 4.25 to 1.00.",
                    ),
                    _citation(
                        "beacon-original",
                        "Beacon Term Loan Agreement",
                        "§7.10(a), p. 92",
                        "Original threshold was 4.00 to 1.00.",
                    ),
                ],
            ),
            facts=deepcopy(COMMON_FACTS),
            unsupported_obligations=[INTEREST_COVERAGE_UNSUPPORTED],
            amendment_note=(
                "Amendment No. 2 controls this quarter; the original 4.00x term is superseded."
            ),
        ),
        CovenantCase(
            id="meridian-evidence-gap",
            name="Meridian: evidence gap requires review",
            narrative=(
                "A proposed EBITDA add-back improves the ratio, but its management "
                "support is missing. The system must not issue a compliant conclusion."
            ),
            agreement="Meridian Revolving Credit Agreement",
            agreement_version="Amendment No. 1",
            test_date="2026-06-30",
            scenario_type="evidence_gap",
            documents=[
                _document(
                    "meridian-original",
                    "Meridian Revolving Credit Agreement",
                    "agreement",
                    "2025-06-01",
                ),
                _document(
                    "meridian-amendment-1",
                    "Meridian Amendment No. 1",
                    "amendment",
                    "2026-01-10",
                    controlling=True,
                    supersedes=["meridian-original:§6.12"],
                ),
            ],
            rule=CovenantRule(
                id="meridian-max-net-leverage",
                name="Maximum Net Leverage Ratio",
                formula_label=(
                    "(Funded debt − unrestricted cash) ÷ "
                    "(EBITDA + approved restructuring add-back)"
                ),
                numerator_keys=["funded_debt"],
                subtract_keys=["unrestricted_cash"],
                denominator_keys=["ebitda", "restructuring_addback"],
                threshold=3.5,
                comparator="<=",
                measurement_period=PERIOD,
                citations=[
                    _citation(
                        "meridian-original",
                        "Meridian Revolving Credit Agreement",
                        "§1.01, p. 38",
                        "Restructuring charges require support certified by an authorized officer.",
                    ),
                    _citation(
                        "meridian-amendment-1",
                        "Meridian Amendment No. 1",
                        "§6.12, p. 77",
                        "Maximum Net Leverage Ratio shall not exceed 3.50 to 1.00.",
                    ),
                ],
            ),
            facts=[
                _fact("funded_debt", "Funded debt", 1200, "Q2 debt schedule", "row 12"),
                _fact(
                    "unrestricted_cash",
                    "Unrestricted cash",
                    100,
                    "Q2 balance sheet",
                    "cash and equivalents note",
                ),
                _fact(
                    "ebitda",
                    "Consolidated EBITDA",
                    270,
                    "Q2 management accounts",
                    "EBITDA bridge",
                ),
                _fact(
                    "restructuring_addback",
                    "Proposed restructuring add-back",
                    80,
                    "Management support request",
                    "not attached",
                    supported=False,
                    requires_review=True,
                ),
            ],
            risk_note=(
                "Candidate arithmetic may be shown, but the conclusion is held pending evidence."
            ),
            unsupported_obligations=[INTEREST_COVERAGE_UNSUPPORTED],
        ),
    ]
    catalog = {case.id: case for case in cases}
    aon = build_aon_term_loan_case()
    # The rule is tested for the Measurement Period ending on the test date;
    # the bundled facts are fiscal-2023, so the policy period guard holds the
    # Aon case in NEEDS_REVIEW instead of showing a real issuer as compliant.
    aon.rule.measurement_period = f"Measurement Period ended {AON_TEST_DATE}"
    catalog[AON_CASE_ID] = aon
    return catalog
