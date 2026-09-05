import unittest

from src.covenant import (
    CovenantWorkflow,
    DraftStatus,
    RunRequest,
    build_demo_workflow,
)
from src.covenant.catalog import build_demo_catalog
from src.covenant.repository import InMemoryRepository


class CovenantWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = build_demo_workflow()

    def test_catalog_exposes_judge_ready_scenarios(self):
        cases = self.workflow.list_cases()

        self.assertEqual(len(cases), 5)
        self.assertIn("aon-term-loan-leverage", {case["id"] for case in cases})
        self.assertEqual(
            {case["scenario_type"] for case in cases},
            {"comparison", "amendment", "evidence_gap"},
        )

    def test_same_financials_have_opposite_contract_results(self):
        aurora = self.workflow.run("aurora-net-leverage")
        beacon = self.workflow.run("beacon-gross-leverage")

        self.assertEqual(aurora.status, DraftStatus.COMPLIANT)
        self.assertEqual(beacon.status, DraftStatus.BREACH)
        self.assertEqual(aurora.calculation.ratio, 3.14)
        self.assertEqual(beacon.calculation.ratio, 4.17)
        self.assertNotEqual(aurora.calculation.formula, beacon.calculation.formula)

    def test_controlling_amendment_replaces_original_threshold(self):
        result = self.workflow.run("beacon-amendment")

        self.assertEqual(result.status, DraftStatus.COMPLIANT)
        self.assertEqual(result.calculation.threshold, 4.25)
        self.assertEqual(result.calculation.original_threshold, 4.0)
        self.assertEqual(result.case["agreement_version"], "Amendment No. 2 (controlling)")

    def test_missing_adjustment_evidence_fails_closed_then_records_decision(self):
        pending = self.workflow.run("meridian-evidence-gap")
        approved = self.workflow.run(
            "meridian-evidence-gap",
            RunRequest(
                reviewer_decision="approve_addback",
                reviewer_name="A. Treasurer",
                reviewer_rationale="Management schedule reconciled to the ledger.",
            ),
        )
        rejected = self.workflow.run(
            "meridian-evidence-gap",
            RunRequest(
                reviewer_decision="reject_addback",
                reviewer_name="A. Treasurer",
                reviewer_rationale="Requested support was not delivered.",
            ),
        )

        self.assertEqual(pending.status, DraftStatus.REVIEW)
        self.assertEqual(approved.status, DraftStatus.COMPLIANT)
        self.assertEqual(rejected.status, DraftStatus.BREACH)
        self.assertEqual(approved.calculation.ratio, 3.14)
        self.assertEqual(rejected.calculation.ratio, 4.07)
        self.assertTrue(any(item.type == "decision" for item in approved.evidence))
        self.assertEqual(len(self.workflow.history("meridian-evidence-gap")), 3)

    def test_review_decision_without_identity_cannot_clear_blocker(self):
        result = self.workflow.run(
            "meridian-evidence-gap",
            RunRequest(reviewer_decision="approve_addback"),
        )

        self.assertEqual(result.status, DraftStatus.REVIEW)
        self.assertIn("named reviewer", result.status_reason)

    def test_review_decision_without_rationale_cannot_clear_blocker(self):
        result = self.workflow.run(
            "meridian-evidence-gap",
            RunRequest(
                reviewer_decision="approve_addback",
                reviewer_name="A. Treasurer",
            ),
        )

        self.assertEqual(result.status, DraftStatus.REVIEW)
        self.assertTrue(
            any(
                issue.code == "REVIEWER_RATIONALE_REQUIRED"
                for issue in result.review_issues
            )
        )

    def test_unresolved_document_precedence_cannot_produce_compliance(self):
        cases = build_demo_catalog()
        for document in cases["aurora-net-leverage"].documents:
            document.controlling = False
        workflow = CovenantWorkflow(InMemoryRepository(cases))

        result = workflow.run("aurora-net-leverage")

        self.assertEqual(result.status, DraftStatus.REVIEW)
        self.assertTrue(
            any(
                issue.code == "DOCUMENT_PRECEDENCE_UNRESOLVED"
                for issue in result.review_issues
            )
        )

    def test_missing_formula_input_cannot_be_silently_treated_as_zero(self):
        cases = build_demo_catalog()
        case = cases["beacon-gross-leverage"]
        case.facts = [fact for fact in case.facts if fact.key != "operating_leases"]
        workflow = CovenantWorkflow(InMemoryRepository(cases))

        result = workflow.run("beacon-gross-leverage")

        self.assertEqual(result.status, DraftStatus.REVIEW)
        self.assertTrue(
            any(issue.code == "MISSING_FINANCIAL_FACT" for issue in result.review_issues)
        )

    def test_certificate_and_audit_events_are_content_addressed(self):
        result = self.workflow.run("aurora-net-leverage")

        self.assertTrue(result.certificate.id.startswith("cert-"))
        self.assertEqual(len(result.certificate.evidence_manifest_hash), 64)
        self.assertEqual(len({event.artifact_hash for event in result.trace}), len(result.trace))
        self.assertEqual(
            [event.sequence for event in result.trace],
            list(range(1, len(result.trace) + 1)),
        )


if __name__ == "__main__":
    unittest.main()
