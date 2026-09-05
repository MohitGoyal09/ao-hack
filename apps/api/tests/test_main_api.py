import unittest

from fastapi.testclient import TestClient

from main import app, revision_store

REVIEWER = {"Authorization": "Bearer demo-user:treasury_reviewer:demo-org"}
OFFICER = {"Authorization": "Bearer officer-1:officer:demo-org"}


class CovenantApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_reports_requested_runtime_stack(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["orchestrator"], "langgraph")
        self.assertEqual(body["agent_transport"], "ag-ui")
        self.assertIn(body["supabase"], {"configured", "offline-demo"})

    def test_case_can_run_end_to_end_over_http(self):
        response = self.client.post(
            "/api/cases/beacon-gross-leverage/run", json={}
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "DRAFT_BREACH")
        self.assertEqual(body["calculation"]["ratio"], "4.17")
        self.assertIsInstance(body["calculation"]["ratio"], str)
        self.assertEqual(body["runtime"]["orchestrator"], "langgraph")
        self.assertGreaterEqual(len(body["trace"]), 7)

    def test_missing_case_is_404(self):
        response = self.client.post("/api/cases/not-a-case/run", json={})

        self.assertEqual(response.status_code, 404)

    def test_ag_ui_agent_route_is_registered(self):
        paths = {route.path for route in app.routes}

        self.assertIn("/ag-ui", paths)

    def test_revision_flow_with_stale_rejection_and_idempotency(self):
        case_id = "beacon-gross-leverage"
        snap = self.client.get(f"/api/cases/{case_id}/snapshot", headers=REVIEWER)
        self.assertEqual(snap.status_code, 200)
        rev1 = snap.json()["revision"]["revision_id"]
        bundle1 = snap.json()["revision"]["input_bundle_hash"]

        # New threshold replaces the current threshold -> new revision.
        created = self.client.post(
            f"/api/cases/{case_id}/revisions",
            json={"expected_parent_revision": rev1, "change_kind": "amendment",
                  "documents": ["amendment-2"], "new_threshold": 4.25},
            headers=REVIEWER,
        )
        self.assertEqual(created.status_code, 200)
        rev2 = created.json()["revision_id"]
        self.assertNotEqual(rev2, rev1)
        self.assertIsInstance(created.json()["revision"]["threshold"], str)

        impact = self.client.get(f"/api/cases/{case_id}/revisions/{rev2}/impact",
                                 headers=REVIEWER)
        self.assertEqual(impact.status_code, 200)
        self.assertTrue(impact.json()["affected_rule_ids"])
        self.assertTrue(impact.json()["stale_artifact_ids"])

        # Stale parent -> 409.
        stale = self.client.post(
            f"/api/cases/{case_id}/revisions",
            json={"expected_parent_revision": rev1, "change_kind": "amendment",
                  "documents": ["amendment-3"]},
            headers=REVIEWER,
        )
        self.assertEqual(stale.status_code, 409)

        # Resolve the fresh review issue; duplicate key + same payload replays.
        snap2 = self.client.get(f"/api/cases/{case_id}/snapshot", headers=REVIEWER)
        bundle2 = snap2.json()["revision"]["input_bundle_hash"]
        issue_id = f"{case_id}-{rev2}-evidence-1"
        payload = {"revision_id": rev2, "expected_bundle_hash": bundle2,
                   "decision_kind": "accept_evidence", "rationale": "verified",
                   "evidence_refs": ["doc:amendment-2"], "idempotency_key": "key-1"}
        first = self.client.post(f"/api/review-issues/{issue_id}/resolve", json=payload,
                                 headers=REVIEWER)
        self.assertEqual(first.status_code, 200)
        replay = self.client.post(f"/api/review-issues/{issue_id}/resolve", json=payload,
                                  headers=REVIEWER)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json(), first.json())

        # Same key + different payload -> conflict.
        clash = dict(payload, rationale="changed mind")
        conflict = self.client.post(f"/api/review-issues/{issue_id}/resolve", json=clash,
                                    headers=REVIEWER)
        self.assertEqual(conflict.status_code, 409)

        # Stale resolve against old revision/bundle -> 409.
        old_issue = f"{case_id}-evidence-1"
        stale_resolve = self.client.post(
            f"/api/review-issues/{old_issue}/resolve",
            json={"revision_id": rev1, "expected_bundle_hash": bundle1,
                  "decision_kind": "accept_evidence", "rationale": "late",
                  "evidence_refs": [], "idempotency_key": "key-2"},
            headers=REVIEWER,
        )
        self.assertEqual(stale_resolve.status_code, 409)

        # Officer approval binds to the exact current package hash.
        snap3 = self.client.get(f"/api/cases/{case_id}/snapshot", headers=OFFICER)
        package_hash = snap3.json()["package_hash"]
        approval = self.client.post(
            f"/api/cases/{case_id}/officer-approval",
            json={"revision_id": rev2, "package_hash": package_hash,
                  "decision": "approved", "reason": "reviewed"},
            headers=OFFICER,
        )
        self.assertEqual(approval.status_code, 200)

        # Old approval cannot authorize the next revision.
        created2 = self.client.post(
            f"/api/cases/{case_id}/revisions",
            json={"expected_parent_revision": rev2, "change_kind": "amendment",
                  "documents": ["amendment-3"]},
            headers=REVIEWER,
        )
        rev3 = created2.json()["revision_id"]
        reused = self.client.post(
            f"/api/cases/{case_id}/officer-approval",
            json={"revision_id": rev2, "package_hash": package_hash,
                  "decision": "approved", "reason": "reused"},
            headers=OFFICER,
        )
        self.assertEqual(reused.status_code, 409)
        wrong_hash = self.client.post(
            f"/api/cases/{case_id}/officer-approval",
            json={"revision_id": rev3, "package_hash": "deadbeef",
                  "decision": "approved", "reason": "wrong hash"},
            headers=OFFICER,
        )
        self.assertEqual(wrong_hash.status_code, 409)


    def test_run_uses_head_revision_threshold(self):
        case_id = "beacon-gross-leverage"
        snap = self.client.get(f"/api/cases/{case_id}/snapshot", headers=REVIEWER)
        head = snap.json()["revision"]["revision_id"]
        created = self.client.post(
            f"/api/cases/{case_id}/revisions",
            json={"expected_parent_revision": head, "change_kind": "amendment",
                  "documents": ["amendment-4-50"], "new_threshold": 4.5},
            headers=REVIEWER,
        )
        self.assertEqual(created.status_code, 200)
        run = self.client.post(f"/api/cases/{case_id}/run", json={})
        self.assertEqual(run.status_code, 200)
        body = run.json()
        self.assertEqual(body["calculation"]["threshold"], "4.50")
        self.assertEqual(body["calculation"]["original_threshold"], "4.00")
        self.assertEqual(body["calculation"]["ratio"], "4.17")
        self.assertEqual(body["status"], "DRAFT_COMPLIANT")
        # Documents accumulate across revisions; the original is never dropped.
        docs = self.client.get(f"/api/cases/{case_id}/snapshot",
                               headers=REVIEWER).json()["documents"]
        self.assertIn("beacon-original", docs)
        self.assertIn("amendment-4-50", docs)

    def test_officer_approval_locks_worker_calculation_when_present(self):
        from unittest.mock import patch

        from src.covenant.pipeline import CasePipeline
        from src.platform.storage import MemoryStorageAdapter
        from test_pipeline import FAKE_FACTS, FAKE_RULE, _job  # discovery: -s tests

        case_id = "aon-term-loan-leverage"
        snap = self.client.get(f"/api/cases/{case_id}/snapshot", headers=OFFICER).json()
        rev = snap["revision"]["revision_id"]
        pipeline = CasePipeline(None, MemoryStorageAdapter(),
                                revision_repository=revision_store)
        version = pipeline.documents.upload(
            organization_id="demo-org", user_id="officer-1", case_id=case_id,
            filename="agreement.pdf", content_type="application/pdf",
            data=b"%PDF-1.4 stand-in", document_role="credit_agreement",
            title="Agreement",
        )
        job = _job(case_id, rev, version.document_id)
        with patch("src.covenant.ingestion.extract_aon_rule", return_value=FAKE_RULE), \
             patch("src.covenant.ingestion.extract_aon_financials", return_value=FAKE_FACTS):
            pipeline.begin(job)
            pipeline.run(job, on_progress=lambda: None)
        snap = self.client.get(f"/api/cases/{case_id}/snapshot", headers=OFFICER).json()
        self.assertEqual(snap["run_state"], "completed")
        self.assertEqual(snap["artifacts"]["calculation"]["ratio"], "3.64")
        issue = snap["review_issues"][0]
        self.assertEqual(issue["status"], "open")
        resolve = self.client.post(
            f"/api/review-issues/{issue['issue_id']}/resolve",
            json={"revision_id": rev, "expected_bundle_hash": snap["revision"]["input_bundle_hash"],
                  "decision_kind": "accept_evidence", "rationale": "verified",
                  "evidence_refs": [f"doc:{version.document_id}"],
                  "idempotency_key": f"artifact-approval-{rev}"},
            headers=OFFICER,
        )
        self.assertEqual(resolve.status_code, 200, resolve.text)
        self.assertEqual(self.client.get(f"/api/cases/{case_id}/snapshot",
                                         headers=OFFICER).json()["package_state"],
                         "ready_for_officer_review")
        approval = self.client.post(
            f"/api/cases/{case_id}/officer-approval",
            json={"revision_id": rev, "package_hash": snap["package_hash"],
                  "decision": "approved", "reason": "reviewed"},
            headers=OFFICER,
        )
        self.assertEqual(approval.status_code, 200, approval.text)
        body = approval.json()
        self.assertEqual(body["approved_ratio"], "3.64")
        self.assertEqual(body["approved_threshold"], "4.00")
        self.assertEqual(body["approved_inputs"]["funded_debt"], "8000.00")
        after = self.client.get(f"/api/cases/{case_id}/snapshot", headers=OFFICER).json()
        self.assertEqual(after["package_state"], "approved_draft")
        self.assertFalse(after["approvals"][-1]["superseded"])

    def test_approval_locks_exact_numbers_and_supersedes(self):
        case_id = "aurora-net-leverage"
        snap = self.client.get(f"/api/cases/{case_id}/snapshot", headers=REVIEWER)
        self.assertEqual(snap.status_code, 200)
        rev1 = snap.json()["revision"]["revision_id"]
        bundle = snap.json()["revision"]["input_bundle_hash"]
        # Resolve the seeded blocking issue so approval can proceed.
        issue_id = f"{case_id}-evidence-1"
        if "rev-1" not in rev1:
            issue_id = f"{case_id}-{rev1}-evidence-1"
        else:
            # ensure_case may already exist from another test; resolve whatever is open.
            pass
        resolve = self.client.post(
            f"/api/review-issues/{issue_id}/resolve",
            json={"revision_id": rev1, "expected_bundle_hash": bundle,
                  "decision_kind": "accept_evidence", "rationale": "verified",
                  "evidence_refs": ["doc:aurora-original"],
                  "idempotency_key": f"lock-test-{rev1}-1"},
            headers=REVIEWER,
        )
        self.assertEqual(resolve.status_code, 200)

        snap2 = self.client.get(f"/api/cases/{case_id}/snapshot", headers=OFFICER)
        package_hash = snap2.json()["package_hash"]
        threshold = snap2.json()["revision"]["threshold"]

        # Drifted threshold in the officer-seen numbers -> 409 naming the number.
        drifted = self.client.post(
            f"/api/cases/{case_id}/officer-approval",
            json={"revision_id": rev1, "package_hash": package_hash,
                  "decision": "approved", "reason": "drift check",
                  "approved_threshold": "3.75"},
            headers=OFFICER,
        )
        self.assertEqual(drifted.status_code, 409)
        self.assertIn("threshold changed from 3.75", drifted.json()["detail"])

        # Correct numbers lock in; response carries legible summary.
        approval = self.client.post(
            f"/api/cases/{case_id}/officer-approval",
            json={"revision_id": rev1, "package_hash": package_hash,
                  "decision": "approved", "reason": "reviewed",
                  "approved_threshold": threshold},
            headers=OFFICER,
        )
        self.assertEqual(approval.status_code, 200)
        body = approval.json()
        self.assertIn("approved_threshold", body)
        self.assertIn("approved_inputs", body)
        self.assertIn("locked_summary", body)
        self.assertIn("this approval locked in:", body["locked_summary"])
        self.assertIn(threshold, body["locked_summary"])
        self.assertIsInstance(body["approved_threshold"], str)

        # New revision supersedes the prior approval...
        created = self.client.post(
            f"/api/cases/{case_id}/revisions",
            json={"expected_parent_revision": rev1, "change_kind": "amendment",
                  "documents": ["amendment-9"], "new_threshold": 4.25},
            headers=REVIEWER,
        )
        self.assertEqual(created.status_code, 200)
        rev2 = created.json()["revision_id"]
        approvals = revision_store.snapshot(case_id)["approvals"]
        old = [a for a in approvals if a["target_revision"] == rev1]
        self.assertTrue(old and all(a["superseded"] for a in old))

        # ...and the superseded approval can never re-authorize, even with its old hash.
        reused = self.client.post(
            f"/api/cases/{case_id}/officer-approval",
            json={"revision_id": rev1, "package_hash": package_hash,
                  "decision": "approved", "reason": "reused"},
            headers=OFFICER,
        )
        self.assertEqual(reused.status_code, 409)


if __name__ == "__main__":
    unittest.main()
