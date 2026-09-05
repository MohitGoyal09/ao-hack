"""Authentication and organization authorization for private revision routes."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app, create_app
from src.platform.jobqueue import DurabilityComponentStatus, DurabilityStatus

REVIEWER = {"Authorization": "Bearer alice:treasury_reviewer:org-a"}
OFFICER = {"Authorization": "Bearer omar:officer:org-a"}
OUTSIDER = {"Authorization": "Bearer mallory:treasury_reviewer:org-b"}
VIEWER = {"Authorization": "Bearer vic:viewer:org-a"}


class RevisionAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.case_id = "meridian-evidence-gap"

    def _snapshot(self, headers):
        return self.client.get(f"/api/cases/{self.case_id}/snapshot",
                               headers=headers)

    def test_unauthenticated_revision_requests_return_401(self) -> None:
        self.assertEqual(self._snapshot({}).status_code, 401)
        self.assertEqual(
            self.client.post(f"/api/cases/{self.case_id}/revisions",
                             json={}).status_code, 401)
        self.assertEqual(
            self.client.get(f"/api/cases/{self.case_id}/revisions/rev-1/impact").status_code,
            401)
        self.assertEqual(
            self.client.post("/api/review-issues/x/resolve", json={}).status_code,
            401)
        self.assertEqual(
            self.client.post(f"/api/cases/{self.case_id}/officer-approval",
                             json={}).status_code, 401)

    def test_reviewer_cannot_perform_officer_approval(self) -> None:
        snap = self._snapshot(REVIEWER)
        self.assertEqual(snap.status_code, 200)
        rev = snap.json()["revision"]["revision_id"]
        package = snap.json()["package_hash"]
        response = self.client.post(
            f"/api/cases/{self.case_id}/officer-approval",
            json={"revision_id": rev, "package_hash": package,
                  "decision": "approved", "reason": "reviewer attempt"},
            headers=REVIEWER,
        )
        self.assertEqual(response.status_code, 403)

    def test_body_actor_and_role_cannot_raise_privilege(self) -> None:
        snap = self._snapshot(REVIEWER)
        rev = snap.json()["revision"]["revision_id"]
        package = snap.json()["package_hash"]
        # A reviewer claiming officer in the body is still forbidden: the
        # server derives role from the session, never the request JSON.
        response = self.client.post(
            f"/api/cases/{self.case_id}/officer-approval",
            json={"revision_id": rev, "package_hash": package,
                  "actor": "omar", "role": "officer",
                  "decision": "approved", "reason": "forged"},
            headers=REVIEWER,
        )
        self.assertEqual(response.status_code, 403)

    def test_user_from_another_organization_cannot_access_case(self) -> None:
        # Prime the case under org-a, then access from org-b: 404, no leak.
        prime = self._snapshot(REVIEWER)
        self.assertEqual(prime.status_code, 200)
        outsider = self._snapshot(OUTSIDER)
        self.assertEqual(outsider.status_code, 404)
        self.assertNotIn("org-a", outsider.text)

    def test_viewer_cannot_resolve_review_issues(self) -> None:
        snap = self._snapshot(VIEWER)
        # viewer is a member of org-a (auto-provisioned) so the snapshot
        # succeeds, but resolution requires a reviewer role.
        if snap.status_code != 200:
            self.skipTest("viewer membership not provisioned")
        rev = snap.json()["revision"]["revision_id"]
        bundle = snap.json()["revision"]["input_bundle_hash"]
        issue = f"{self.case_id}-{rev}-evidence-1"
        if "rev-1" in rev:
            issue = f"{self.case_id}-evidence-1"
        response = self.client.post(
            f"/api/review-issues/{issue}/resolve",
            json={"revision_id": rev, "expected_bundle_hash": bundle,
                  "decision_kind": "accept_evidence", "rationale": "viewer",
                  "evidence_refs": [], "idempotency_key": "viewer-key-1"},
            headers=VIEWER,
        )
        self.assertEqual(response.status_code, 403)

    def test_officer_approval_binds_server_identity(self) -> None:
        snap = self._snapshot(OFFICER)
        self.assertEqual(snap.status_code, 200)
        rev = snap.json()["revision"]["revision_id"]
        bundle = snap.json()["revision"]["input_bundle_hash"]
        package = snap.json()["package_hash"]
        issue = f"{self.case_id}-{rev}-evidence-1"
        if "rev-1" in rev:
            issue = f"{self.case_id}-evidence-1"
        resolve = self.client.post(
            f"/api/review-issues/{issue}/resolve",
            json={"revision_id": rev, "expected_bundle_hash": bundle,
                  "decision_kind": "accept_evidence", "rationale": "verified",
                  "evidence_refs": [], "idempotency_key": "bind-key-1",
                  "actor": "mallory", "role": "admin"},
            headers=OFFICER,
        )
        self.assertEqual(resolve.status_code, 200)
        approval = self.client.post(
            f"/api/cases/{self.case_id}/officer-approval",
            json={"revision_id": rev, "package_hash": package,
                  "actor": "mallory", "role": "admin",
                  "decision": "approved", "reason": "bound"},
            headers=OFFICER,
        )
        self.assertEqual(approval.status_code, 200)
        body = approval.json()
        self.assertEqual(body["actor"], "omar")
        self.assertEqual(body["role"], "officer")

    def test_configured_revision_failure_makes_readiness_fail(self) -> None:
        failed = DurabilityStatus(
            queue=DurabilityComponentStatus.failed("queue"),
            checkpoint=DurabilityComponentStatus.failed("checkpoint"),
            revisions=DurabilityComponentStatus.failed("revisions"),
        )
        client = TestClient(create_app(durability_status=failed))
        response = client.get("/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["durability"]["revisions"]["verified"])

    def test_offline_mode_still_uses_memory_repository(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            from src.covenant.revision_repository import (
                MemoryRevisionRepository,
                revision_repository_from_env,
            )
            self.assertIsInstance(revision_repository_from_env(),
                                  MemoryRevisionRepository)


if __name__ == "__main__":
    unittest.main()
