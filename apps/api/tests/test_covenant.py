import unittest

from src.covenant import DEMO_CASES, DraftStatus, RunRequest, run_case


class CovenantPolicyTests(unittest.TestCase):
    def test_same_financials_can_have_opposite_contract_results(self):
        aurora = run_case(DEMO_CASES["aurora-net-leverage"], RunRequest())
        beacon = run_case(DEMO_CASES["beacon-gross-leverage"], RunRequest())

        self.assertEqual(aurora["status"], DraftStatus.COMPLIANT)
        self.assertEqual(beacon["status"], DraftStatus.BREACH)
        self.assertEqual(aurora["calculation"]["ratio"], 3.14)
        self.assertEqual(beacon["calculation"]["ratio"], 4.17)

    def test_controlling_amendment_changes_the_result(self):
        result = run_case(DEMO_CASES["beacon-amendment"], RunRequest())

        self.assertEqual(result["status"], DraftStatus.COMPLIANT)
        self.assertEqual(result["calculation"]["threshold"], 4.25)
        self.assertEqual(result["calculation"]["original_threshold"], 4.0)

    def test_missing_evidence_fails_closed_to_review(self):
        case = DEMO_CASES["meridian-evidence-gap"]
        pending = run_case(case, RunRequest())
        approved = run_case(case, RunRequest(reviewer_decision="approve_addback"))
        rejected = run_case(case, RunRequest(reviewer_decision="reject_addback"))

        self.assertEqual(pending["status"], DraftStatus.REVIEW)
        self.assertEqual(pending["blocking_issues"], case.required_evidence)
        self.assertEqual(approved["status"], DraftStatus.COMPLIANT)
        self.assertEqual(rejected["status"], DraftStatus.BREACH)


if __name__ == "__main__":
    unittest.main()
