"""``POST /api/cases`` (fresh case from a catalog template) and ``GET /api/cases``.

Offline scope: the memory revision repository plus the catalog resolver bound
in ``main``. A created case must behave like a curated one on every route
that looks a case id up (describe, snapshot, run, documents, list).
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from main import app

TEMPLATE = "aon-term-loan-leverage"
OFFICER = {"Authorization": "Bearer case-maker:officer:demo-org"}
VIEWER = {"Authorization": "Bearer case-viewer:viewer:demo-org"}
OUTSIDER = {"Authorization": "Bearer case-outsider:officer:org-nobody"}
PDF = b"%PDF-1.4 fake covenant agreement content\n"


class CreateCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def _create(self, headers: dict = OFFICER, **body):
        return self.client.post("/api/cases", headers=headers,
                                json={"template_case_id": TEMPLATE, **body})

    def test_requires_auth(self) -> None:
        self.assertEqual(self._create(headers={}).status_code, 401)
        self.assertEqual(self.client.get("/api/cases").status_code, 401)

    def test_viewer_is_forbidden(self) -> None:
        self.assertEqual(self._create(headers=VIEWER).status_code, 403)

    def test_unknown_template_is_404(self) -> None:
        response = self._create(template_case_id="not-a-template")
        self.assertEqual(response.status_code, 404)

    def test_bad_test_date_is_422(self) -> None:
        self.assertEqual(self._create(test_date="Q1").status_code, 422)

    def test_created_case_is_resolvable_everywhere(self) -> None:
        created = self._create(name="Aon Q1 2024", test_date="2024-03-31")
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        case_id = body["case_id"]
        self.assertTrue(case_id.startswith("aon-q1-2024-"), case_id)
        self.assertEqual(body, {"case_id": case_id, "organization_id": "demo-org",
                                "template_case_id": TEMPLATE, "name": "Aon Q1 2024"})

        # Public describe: the given name, the template's covenant and test date override.
        template = self.client.get(f"/api/cases/{TEMPLATE}").json()
        info = self.client.get(f"/api/cases/{case_id}")
        self.assertEqual(info.status_code, 200)
        self.assertEqual(info.json()["name"], "Aon Q1 2024")
        self.assertEqual(info.json()["test_date"], "2024-03-31")
        self.assertEqual(info.json()["covenant_name"], template["covenant_name"])

        # Snapshot: rev-1 seeded with the template's rule and threshold.
        snap = self.client.get(f"/api/cases/{case_id}/snapshot", headers=OFFICER)
        self.assertEqual(snap.status_code, 200, snap.text)
        self.assertEqual(snap.json()["revision"]["revision_id"], "rev-1")
        self.assertEqual(snap.json()["revision"]["rule_id"], "aon-max-consolidated-leverage")
        self.assertEqual(snap.json()["revision"]["threshold"], "4.00")
        self.assertEqual(snap.json()["run_state"], "pending")
        self.assertEqual(snap.json()["open_review_issues"], 0)
        self.assertEqual(snap.json()["documents"], [])

        # List: member-scoped, carries name / head run_state / template.
        listed = self.client.get("/api/cases", headers=OFFICER)
        self.assertEqual(listed.status_code, 200)
        mine = next(c for c in listed.json() if c["case_id"] == case_id)
        self.assertEqual(mine["name"], "Aon Q1 2024")
        self.assertEqual(mine["template_case_id"], TEMPLATE)
        self.assertEqual(mine["run_state"], "pending")
        self.assertTrue(mine["created_at"])
        self.assertNotIn(case_id, [c["case_id"] for c in
                                   self.client.get("/api/cases", headers=OUTSIDER).json()])

        # Run: the deterministic workflow resolves the new id to the template
        # (Aon stays NEEDS_REVIEW on the period mismatch, never a verdict).
        run = self.client.post(f"/api/cases/{case_id}/run", json={}, headers=OFFICER)
        self.assertEqual(run.status_code, 200, run.text)
        self.assertEqual(run.json()["status"], "NEEDS_REVIEW")
        self.assertEqual(run.json()["case"]["id"], case_id)
        self.assertEqual(run.json()["case"]["name"], "Aon Q1 2024")

        # Upload: intake versions a document on the new case and enqueues a job.
        upload = self.client.post(
            f"/api/cases/{case_id}/documents", headers=OFFICER,
            files={"file": ("agreement.pdf", PDF, "application/pdf")},
            data={"document_role": "credit_agreement", "title": "Aon agreement"},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(upload.json()["revision_id"], "rev-2")
        self.assertIsNone(upload.json()["job_id"])

        # Tenant isolation and the curated catalog are untouched.
        self.assertEqual(self.client.get(f"/api/cases/{case_id}/snapshot",
                                         headers=OUTSIDER).status_code, 404)
        self.assertNotIn(case_id, [c["id"] for c in self.client.get("/api/demo-cases").json()])

    def test_each_create_is_a_fresh_case(self) -> None:
        first = self._create(name="Take one").json()["case_id"]
        second = self._create(name="Take one").json()["case_id"]
        self.assertNotEqual(first, second)
        self.assertEqual(self.client.get(f"/api/cases/{second}/snapshot", headers=OFFICER)
                         .json()["revision"]["revision_id"], "rev-1")
        # Name defaults to the template's when omitted.
        self.assertEqual(self._create().json()["name"],
                         self.client.get(f"/api/cases/{TEMPLATE}").json()["name"])


if __name__ == "__main__":
    unittest.main()
