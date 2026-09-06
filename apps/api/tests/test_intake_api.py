"""Document intake routes + ingest tool (offline demo scope)."""

from __future__ import annotations

import unittest
import uuid

from fastapi.testclient import TestClient

from main import ALLOWED_ROLES, MAX_BYTES, app
from src.agent import ingest_covenant_document

REVIEWER = {"Authorization": "Bearer u:treasury_reviewer:demo-org"}
OUTSIDER = {"Authorization": "Bearer x:treasury_reviewer:other-org"}
VIEWER = {"Authorization": "Bearer v:viewer:demo-org"}

CASE_ID = "beacon-amendment"
PDF_BYTES = b"%PDF-1.4 fake covenant agreement content\n"


def _valid_role() -> str:
    return sorted(ALLOWED_ROLES)[0]


def _upload(client, case_id, headers, *, data=PDF_BYTES, filename="agreement.pdf",
            content_type="application/pdf", document_role=None, title="Agreement",
            document_id=None, extra_forms=None):
    forms = {
        "document_role": document_role or _valid_role(),
        "title": title,
    }
    if document_id is not None:
        forms["document_id"] = document_id
    if extra_forms:
        forms.update(extra_forms)
    files = {"file": (filename, data, content_type)}
    return client.post(f"/api/cases/{case_id}/documents", files=files,
                       data=forms, headers=headers)


class IntakeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        # Catalog templates are read-only: every upload test mints a fresh
        # derived working case (also the demo/QA reset affordance).
        created = self.client.post(
            "/api/cases",
            json={"template_case_id": CASE_ID, "name": "Intake probe"},
            headers=REVIEWER,
        )
        assert created.status_code == 200, created.text
        self.case_id = created.json()["case_id"]

    def test_unauthenticated_upload_returns_401(self) -> None:
        response = _upload(self.client, self.case_id, {})
        self.assertEqual(response.status_code, 401)

    def test_happy_path_upload_registers_version_and_waits_for_agent(self) -> None:
        response = _upload(self.client, self.case_id, REVIEWER)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        for key in ("document_id", "version_id", "version_number", "sha256",
                    "extraction_state", "revision_id", "job_id"):
            self.assertIn(key, body)
        self.assertNotIn("data", body)
        self.assertNotIn("content", body)

        self.assertIsNone(body["job_id"])

        meta = self.client.get(f"/api/documents/{body['document_id']}",
                               headers=REVIEWER)
        self.assertEqual(meta.status_code, 200, meta.text)
        meta_body = meta.json()
        self.assertEqual(meta_body.get("document_id"), body["document_id"])
        for forbidden in ("data", "bytes", "content", "file_bytes"):
            self.assertNotIn(forbidden, meta_body)

    def test_second_upload_with_document_id_bumps_version(self) -> None:
        document_id = f"intake-doc-{uuid.uuid4().hex[:8]}"
        first = _upload(self.client, self.case_id, REVIEWER, document_id=document_id)
        self.assertEqual(first.status_code, 200, first.text)
        second = _upload(self.client, self.case_id, REVIEWER, document_id=document_id,
                         data=b"%PDF-1.4 second version\n")
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["document_id"], document_id)
        self.assertEqual(first.json()["document_id"], document_id)
        self.assertEqual(second.json()["version_number"],
                         first.json()["version_number"] + 1)
        self.assertNotEqual(second.json()["version_id"], first.json()["version_id"])
        self.assertNotEqual(second.json()["revision_id"], first.json()["revision_id"])

    def test_oversize_upload_returns_413(self) -> None:
        big = b"x" * (int(MAX_BYTES) + 1)
        response = _upload(self.client, self.case_id, REVIEWER, data=big)
        self.assertEqual(response.status_code, 413)

    def test_unsupported_media_returns_422(self) -> None:
        response = _upload(
            self.client, self.case_id, REVIEWER,
            data=b"MZ fake executable",
            filename="evil.exe",
            content_type="application/x-msdownload",
        )
        self.assertEqual(response.status_code, 422)

    def test_bad_document_role_returns_422(self) -> None:
        bad_role = "not-a-real-role-xyz"
        self.assertNotIn(bad_role, set(ALLOWED_ROLES))
        response = _upload(self.client, self.case_id, REVIEWER,
                           document_role=bad_role)
        self.assertEqual(response.status_code, 422)

    def test_outsider_cannot_post_or_get_primed_case(self) -> None:
        primed = _upload(self.client, self.case_id, REVIEWER)
        self.assertEqual(primed.status_code, 200, primed.text)
        document_id = primed.json()["document_id"]

        outsider_post = _upload(self.client, self.case_id, OUTSIDER)
        self.assertEqual(outsider_post.status_code, 404)
        self.assertNotIn("demo-org", outsider_post.text)

        outsider_get = self.client.get(f"/api/documents/{document_id}",
                                       headers=OUTSIDER)
        self.assertEqual(outsider_get.status_code, 404)
        self.assertNotIn("demo-org", outsider_get.text)

    def test_viewer_upload_is_forbidden(self) -> None:
        prime = self.client.get(f"/api/cases/{self.case_id}/snapshot", headers=REVIEWER)
        self.assertEqual(prime.status_code, 200, prime.text)
        response = _upload(self.client, self.case_id, VIEWER)
        self.assertEqual(response.status_code, 403)

    def test_agent_tool_rejects_filesystem_path(self) -> None:
        with self.assertRaises(ValueError):
            ingest_covenant_document("any-case", "a/b", "agreement")
        with self.assertRaises(ValueError):
            ingest_covenant_document("any-case", "../secret", "financials")


if __name__ == "__main__":
    unittest.main()
