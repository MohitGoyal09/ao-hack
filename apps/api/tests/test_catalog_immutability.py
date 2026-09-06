"""Catalog template immutability (G0.7): prepared cases are read-only.

Direct mutation of a prepared catalog case -- revisions, document upload,
review resolution, officer approval -- must be rejected with a 4xx that
points at ``POST /api/cases``. Working state lives on derived cases minted
by ``POST /api/cases`` (fresh id, ``rev-1``). Reads (describe, snapshot,
run, impact, jobs, events) keep working on catalog ids.

These tests FAIL before the fix (mutations return 200 on the shared
template identity) and PASS after it.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from main import app

REVIEWER = {"Authorization": "Bearer catalog-reviewer:treasury_reviewer:demo-org"}
OFFICER = {"Authorization": "Bearer catalog-officer:officer:demo-org"}
# meridian-evidence-gap is owned by org-a in the jobs/auth suites
# (first-primer-wins offline); join it instead of fighting over it.
ORG_A_REVIEWER = {"Authorization": "Bearer catalog-reviewer:treasury_reviewer:org-a"}
ORG_A_OFFICER = {"Authorization": "Bearer catalog-officer:officer:org-a"}
PDF = b"%PDF-1.4 fake covenant agreement content\n"


def _head(client: TestClient, case_id: str, headers: dict) -> dict:
    snap = client.get(f"/api/cases/{case_id}/snapshot", headers=headers)
    assert snap.status_code == 200, snap.text
    return snap.json()


def _open_issue(client: TestClient, case_id: str, headers: dict) -> tuple[str, str, str]:
    snap = _head(client, case_id, headers)
    rev = snap["revision"]["revision_id"]
    bundle = snap["revision"]["input_bundle_hash"]
    issues = [i for i in snap["review_issues"] if i["status"] == "open"]
    assert issues, f"no open issue on {case_id}@{rev}"
    return issues[0]["issue_id"], rev, bundle


class CatalogImmutabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_revision_on_catalog_is_rejected_with_derive_hint(self) -> None:
        snap = _head(self.client, "beacon-gross-leverage", REVIEWER)
        response = self.client.post(
            "/api/cases/beacon-gross-leverage/revisions",
            json={"expected_parent_revision": snap["revision"]["revision_id"],
                   "change_kind": "amendment", "documents": ["amendment-x"]},
            headers=REVIEWER,
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("POST /api/cases", response.text)
        self.assertIn("beacon-gross-leverage", response.text)

    def test_upload_on_catalog_is_rejected(self) -> None:
        response = self.client.post(
            "/api/cases/beacon-amendment/documents", headers=REVIEWER,
            files={"file": ("agreement.pdf", PDF, "application/pdf")},
            data={"document_role": "credit_agreement", "title": "Agreement"},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("POST /api/cases", response.text)

    def test_resolve_on_catalog_issue_is_rejected(self) -> None:
        issue, rev, bundle = _open_issue(
            self.client, "meridian-evidence-gap", ORG_A_REVIEWER)
        response = self.client.post(
            f"/api/review-issues/{issue}/resolve",
            json={"revision_id": rev, "expected_bundle_hash": bundle,
                   "decision_kind": "accept_evidence", "rationale": "verified",
                   "evidence_refs": [], "idempotency_key": "catalog-resolve-1"},
            headers=ORG_A_REVIEWER,
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("POST /api/cases", response.text)

    def test_officer_approval_on_catalog_is_rejected(self) -> None:
        snap = _head(self.client, "meridian-evidence-gap", ORG_A_OFFICER)
        response = self.client.post(
            "/api/cases/meridian-evidence-gap/officer-approval",
            json={"revision_id": snap["revision"]["revision_id"],
                   "package_hash": snap["package_hash"],
                   "decision": "approved", "reason": "demo"},
            headers=ORG_A_OFFICER,
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("POST /api/cases", response.text)

    def test_reviewer_approval_still_forbidden_before_template_guard(self) -> None:
        snap = _head(self.client, "meridian-evidence-gap", ORG_A_REVIEWER)
        response = self.client.post(
            "/api/cases/meridian-evidence-gap/officer-approval",
            json={"revision_id": snap["revision"]["revision_id"],
                   "package_hash": snap["package_hash"],
                   "decision": "approved", "reason": "reviewer attempt"},
            headers=ORG_A_REVIEWER,
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_catalog_reads_still_work(self) -> None:
        case_id = "aurora-net-leverage"
        self.assertEqual(self.client.get(f"/api/cases/{case_id}").status_code, 200)
        snap = _head(self.client, case_id, REVIEWER)
        rev = snap["revision"]["revision_id"]
        self.assertEqual(
            self.client.get(f"/api/cases/{case_id}/revisions/{rev}/impact",
                            headers=REVIEWER).status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/cases/{case_id}/jobs", headers=REVIEWER).status_code,
            200)
        self.assertEqual(
            self.client.get(f"/api/cases/{case_id}/events", headers=REVIEWER).status_code,
            200)
        self.assertEqual(
            self.client.post(f"/api/cases/{case_id}/run", json={}).status_code, 200)

    def test_derived_case_is_mutable_and_freshly_minted(self) -> None:
        first = self.client.post(
            "/api/cases", headers=REVIEWER,
            json={"template_case_id": "beacon-gross-leverage",
                   "name": "Catalog probe one"})
        self.assertEqual(first.status_code, 200, first.text)
        case_id = first.json()["case_id"]
        self.assertNotEqual(case_id, "beacon-gross-leverage")

        snap = _head(self.client, case_id, REVIEWER)
        self.assertEqual(snap["revision"]["revision_id"], "rev-1")

        created = self.client.post(
            f"/api/cases/{case_id}/revisions",
            json={"expected_parent_revision": "rev-1",
                   "change_kind": "amendment", "documents": ["amendment-x"],
                   "new_threshold": 4.25},
            headers=REVIEWER,
        )
        self.assertEqual(created.status_code, 200, created.text)
        rev2 = created.json()["revision_id"]

        snap2 = _head(self.client, case_id, REVIEWER)
        issue = snap2["review_issues"][0]["issue_id"]
        resolve = self.client.post(
            f"/api/review-issues/{issue}/resolve",
            json={"revision_id": rev2,
                   "expected_bundle_hash": snap2["revision"]["input_bundle_hash"],
                   "decision_kind": "accept_evidence", "rationale": "verified",
                   "evidence_refs": ["doc:amendment-x"],
                   "idempotency_key": "catalog-derived-resolve-1"},
            headers=REVIEWER,
        )
        self.assertEqual(resolve.status_code, 200, resolve.text)

        upload = self.client.post(
            f"/api/cases/{case_id}/documents", headers=REVIEWER,
            files={"file": ("agreement.pdf", PDF, "application/pdf")},
            data={"document_role": "credit_agreement", "title": "Agreement"},
        )
        self.assertEqual(upload.status_code, 200, upload.text)

        # Re-deriving mints another isolated working copy at rev-1: the
        # reliable demo/QA reset (no shared template state is ever reused).
        second = self.client.post(
            "/api/cases", headers=REVIEWER,
            json={"template_case_id": "beacon-gross-leverage",
                   "name": "Catalog probe two"})
        self.assertEqual(second.status_code, 200, second.text)
        other = second.json()["case_id"]
        self.assertNotEqual(other, case_id)
        self.assertEqual(_head(self.client, other, REVIEWER)["revision"]["revision_id"],
                         "rev-1")


if __name__ == "__main__":
    unittest.main()
