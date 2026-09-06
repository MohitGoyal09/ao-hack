"""Regression: review resolution must never produce an approvable package.

Release-blocking contradiction under test::

    accept issue -> run still waiting_review + result NEEDS_REVIEW
    -> package ready_for_officer_review -> officer approval 200

Required behavior: resolving an issue only records the decision and queues
a durable recalculation for the same revision. Officer approval succeeds
only after the current run completes with zero blocking issues and a
current calculation artifact. ``request_document`` / ``mark_unresolved``
stay blocking. These tests FAIL against the unsafe implementation.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

import main
from main import app

REVIEWER = {"Authorization": "Bearer safety-reviewer:treasury_reviewer:demo-org"}
OFFICER = {"Authorization": "Bearer safety-officer:officer:demo-org"}


def drain_recalculation_jobs(max_passes: int = 25) -> None:
    """Run the offline worker until the memory queue is idle.

    Mirrors the in-process worker (``INPROCESS_WORKER``) that drains uploads
    under uvicorn; the test client runs without lifespan so tests drive it
    explicitly. The pipeline is bound to the app revision repository so
    run_state, events and artifacts land in the snapshot.
    """
    from src.covenant.pipeline import CasePipeline
    from src.platform.storage import MemoryStorageAdapter
    from src.platform.worker import Worker

    repo = main.revision_repository
    pipeline = CasePipeline(None, MemoryStorageAdapter(),
                            revision_repository=repo)
    pipeline.case_provider = _fixture_case
    store = main.default_durability_runtime.job_store
    # The pipeline stays bound: the snapshot reads artifacts through the
    # bound pipeline, exactly like the in-process worker under uvicorn.
    # Cases are unique per test so no state leaks across tests.
    worker = Worker(store, pipeline, worker_id="safety-test")
    for _ in range(max_passes):
        if worker.run_once() == "idle":
            return


def _fixture_case(case_id: str):
    """Authoritative fixture case for recalculation when no upload exists."""
    return main.workflow._repository.get_case(case_id)  # noqa: SLF001


class ReviewApprovalSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        created = self.client.post(
            "/api/cases",
            json={"template_case_id": "aurora-net-leverage",
                  "name": "Safety contradiction probe"},
            headers=REVIEWER,
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.case_id = created.json()["case_id"]
        revised = self.client.post(
            f"/api/cases/{self.case_id}/revisions",
            json={"expected_parent_revision": "rev-1",
                  "change_kind": "supporting_evidence",
                  "documents": ["safety-review-evidence"]},
            headers=REVIEWER,
        )
        self.assertEqual(revised.status_code, 200, revised.text)
        snap = self.client.get(f"/api/cases/{self.case_id}/snapshot",
                               headers=REVIEWER).json()
        self.rev = snap["revision"]["revision_id"]
        self.bundle = snap["revision"]["input_bundle_hash"]
        self.issue = snap["review_issues"][0]["issue_id"]

    def _resolve(self, kind: str, key: str, rationale: str = "reviewed"):
        return self.client.post(
            f"/api/review-issues/{self.issue}/resolve",
            json={"revision_id": self.rev, "expected_bundle_hash": self.bundle,
                  "decision_kind": kind, "rationale": rationale,
                  "evidence_refs": ["doc:aurora-original"],
                  "idempotency_key": key},
            headers=REVIEWER,
        )

    def _approve(self):
        snap = self.client.get(f"/api/cases/{self.case_id}/snapshot",
                               headers=OFFICER).json()
        return self.client.post(
            f"/api/cases/{self.case_id}/officer-approval",
            json={"revision_id": self.rev,
                  "package_hash": snap["package_hash"],
                  "decision": "approved", "reason": "reviewed"},
            headers=OFFICER,
        )

    def test_accept_leaves_package_draft_and_run_not_completed(self):
        resolve = self._resolve("accept_evidence", "safety-accept-1")
        self.assertEqual(resolve.status_code, 200, resolve.text)
        snap = self.client.get(f"/api/cases/{self.case_id}/snapshot",
                               headers=REVIEWER).json()
        # Never optimistically ready from the resolve response.
        self.assertEqual(snap["package_state"], "draft")
        self.assertNotEqual(snap["run_state"], "completed")

    def test_approval_rejected_while_recalculation_pending(self):
        resolve = self._resolve("accept_evidence", "safety-pending-1")
        self.assertEqual(resolve.status_code, 200, resolve.text)
        approval = self._approve()
        self.assertEqual(approval.status_code, 409, approval.text)

    def test_request_document_remains_blocking(self):
        resolve = self._resolve("request_document", "safety-reqdoc-1",
                                rationale="need the Q1 bank statement")
        self.assertEqual(resolve.status_code, 200, resolve.text)
        snap = self.client.get(f"/api/cases/{self.case_id}/snapshot",
                               headers=REVIEWER).json()
        self.assertGreaterEqual(snap["open_review_issues"], 1)
        self.assertEqual(snap["package_state"], "draft")
        approval = self._approve()
        self.assertEqual(approval.status_code, 409, approval.text)

    def test_reject_and_correct_invalidate_outputs(self):
        for kind, key in (("reject_evidence", "safety-rej-1"),
                          ("correct_mapping", "safety-cor-1")):
            with self.subTest(decision_kind=kind):
                created = self.client.post(
                    "/api/cases",
                    json={"template_case_id": "aurora-net-leverage",
                          "name": f"Safety {kind} probe"},
                    headers=REVIEWER,
                )
                case_id = created.json()["case_id"]
                snap = self.client.get(f"/api/cases/{case_id}/snapshot",
                                       headers=REVIEWER).json()
                revised = self.client.post(
                    f"/api/cases/{case_id}/revisions",
                    json={"expected_parent_revision": snap["revision"]["revision_id"],
                          "change_kind": "supporting_evidence",
                          "documents": [f"{kind}-evidence"]},
                    headers=REVIEWER,
                )
                self.assertEqual(revised.status_code, 200, revised.text)
                snap = self.client.get(f"/api/cases/{case_id}/snapshot",
                                       headers=REVIEWER).json()
                rev = snap["revision"]["revision_id"]
                bundle = snap["revision"]["input_bundle_hash"]
                issue = snap["review_issues"][0]["issue_id"]
                resolve = self.client.post(
                    f"/api/review-issues/{issue}/resolve",
                    json={"revision_id": rev,
                          "expected_bundle_hash": bundle,
                          "decision_kind": kind, "rationale": "reviewed",
                          "evidence_refs": ["doc:aurora-original"],
                          "idempotency_key": key},
                    headers=REVIEWER,
                )
                self.assertEqual(resolve.status_code, 200, resolve.text)
                after = self.client.get(f"/api/cases/{case_id}/snapshot",
                                        headers=REVIEWER).json()
                self.assertEqual(after["package_state"], "draft")
                self.assertNotEqual(after["run_state"], "completed")

    def test_full_safe_flow_ends_in_approval(self):
        resolve = self._resolve("accept_evidence", "safety-flow-1")
        self.assertEqual(resolve.status_code, 200, resolve.text)
        body = resolve.json()
        self.assertIn(body.get("recalculation"), {"queued", "completed"})
        # Durable recomputation for the same revision finishes the run.
        drain_recalculation_jobs()
        snap = self.client.get(f"/api/cases/{self.case_id}/snapshot",
                               headers=OFFICER).json()
        self.assertEqual(snap["run_state"], "completed")
        self.assertEqual(snap["open_review_issues"], 0)
        self.assertEqual(snap["package_state"], "ready_for_officer_review")
        self.assertIn("calculation", snap["artifacts"])
        jobs = self.client.get(
            f"/api/cases/{self.case_id}/jobs", headers=OFFICER).json()
        self.assertTrue(jobs)
        self.assertTrue(all(job["state"] == "completed" for job in jobs), jobs)
        self.assertTrue(all(job["last_error"] is None for job in jobs), jobs)
        approval = self._approve()
        self.assertEqual(approval.status_code, 200, approval.text)
        final_state = self.client.get(
            f"/api/cases/{self.case_id}/snapshot", headers=OFFICER).json()
        self.assertEqual(final_state["package_state"], "approved_draft")


if __name__ == "__main__":
    unittest.main()
