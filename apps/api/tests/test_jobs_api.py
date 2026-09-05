"""Job list/cancel API routes (offline demo scope)."""

from __future__ import annotations

import unittest
import uuid

from fastapi.testclient import TestClient

from main import app

REVIEWER = {"Authorization": "Bearer alice:treasury_reviewer:org-a"}
VIEWER = {"Authorization": "Bearer vic:viewer:org-a"}
OUTSIDER = {"Authorization": "Bearer mallory:treasury_reviewer:org-b"}

CASE_ID = "meridian-evidence-gap"

EXPECTED_KEYS = {"job_id", "revision_id", "state", "attempt_count",
                 "fencing_token", "lease_owner", "last_error"}


def _enqueue(case_id: str, revision_id: str):
    return app.state.durability_runtime.job_store.enqueue(
        case_id, revision_id, {"seed": True})


class JobsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.store = app.state.durability_runtime.job_store

    def _prime(self, headers=REVIEWER):
        return self.client.get(f"/api/cases/{CASE_ID}/jobs", headers=headers)

    def test_unauthenticated_returns_401(self) -> None:
        self.assertEqual(
            self.client.get(f"/api/cases/{CASE_ID}/jobs").status_code, 401)
        self.assertEqual(
            self.client.post("/api/jobs/some-job/cancel").status_code, 401)

    def test_unknown_case_returns_404(self) -> None:
        response = self.client.get("/api/cases/not-a-case/jobs",
                                   headers=REVIEWER)
        self.assertEqual(response.status_code, 404)

    def test_unknown_job_returns_404(self) -> None:
        response = self.client.post("/api/jobs/no-such-job/cancel",
                                    headers=REVIEWER)
        self.assertEqual(response.status_code, 404)
        self.assertIn("Unknown job", response.json()["detail"])

    def test_outsider_gets_404_on_primed_case_routes(self) -> None:
        prime = self._prime(REVIEWER)
        self.assertEqual(prime.status_code, 200)
        outsider_list = self.client.get(f"/api/cases/{CASE_ID}/jobs",
                                        headers=OUTSIDER)
        self.assertEqual(outsider_list.status_code, 404)
        self.assertNotIn("org-a", outsider_list.text)
        # An outsider cannot cancel a job from the primed case either.
        job = _enqueue(CASE_ID, f"outsider-rev-{uuid.uuid4().hex[:8]}")
        try:
            denied = self.client.post(f"/api/jobs/{job.id}/cancel",
                                      headers=OUTSIDER)
            self.assertEqual(denied.status_code, 404)
            self.assertIn("Unknown job", denied.json()["detail"])
            self.assertNotIn("org-a", denied.text)
            self.assertEqual(self.store.get(job.id).state, "queued")
        finally:
            self.client.post(f"/api/jobs/{job.id}/cancel", headers=REVIEWER)

    def test_list_returns_seeded_jobs_newest_first(self) -> None:
        self.assertEqual(self._prime().status_code, 200)
        first = _enqueue(CASE_ID, f"list-rev-a-{uuid.uuid4().hex[:8]}")
        second = _enqueue(CASE_ID, f"list-rev-b-{uuid.uuid4().hex[:8]}")
        try:
            response = self.client.get(f"/api/cases/{CASE_ID}/jobs",
                                       headers=REVIEWER)
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertLessEqual(len(body), 50)
            mine = [row for row in body
                    if row["revision_id"] in (first.revision_id,
                                              second.revision_id)]
            self.assertEqual([row["job_id"] for row in mine],
                             [second.id, first.id])
            for row in body:
                self.assertEqual(set(row.keys()), EXPECTED_KEYS)
        finally:
            self.client.post(f"/api/jobs/{first.id}/cancel",
                             headers=REVIEWER)
            self.client.post(f"/api/jobs/{second.id}/cancel",
                             headers=REVIEWER)

    def test_list_caps_at_50(self) -> None:
        self.assertEqual(self._prime().status_code, 200)
        ids = [_enqueue(CASE_ID, f"cap-{uuid.uuid4().hex[:8]}").id
               for _ in range(55)]
        try:
            response = self.client.get(f"/api/cases/{CASE_ID}/jobs",
                                       headers=REVIEWER)
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(len(body), 50)
            self.assertEqual(body[0]["job_id"], ids[-1])
        finally:
            for job_id in ids:
                self.client.post(f"/api/jobs/{job_id}/cancel",
                                 headers=REVIEWER)

    def test_cancel_queued_job_and_idempotent(self) -> None:
        self.assertEqual(self._prime().status_code, 200)
        job = _enqueue(CASE_ID, f"cancel-rev-{uuid.uuid4().hex[:8]}")
        response = self.client.post(f"/api/jobs/{job.id}/cancel",
                                    headers=REVIEWER)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(),
                         {"job_id": job.id, "state": "cancelled"})
        again = self.client.post(f"/api/jobs/{job.id}/cancel",
                                 headers=REVIEWER)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json(),
                         {"job_id": job.id, "state": "cancelled"})
        self.assertEqual(self.store.get(job.id).state, "cancelled")

    def test_any_member_role_may_cancel(self) -> None:
        self.assertEqual(self._prime().status_code, 200)
        job = _enqueue(CASE_ID, f"viewer-rev-{uuid.uuid4().hex[:8]}")
        response = self.client.post(f"/api/jobs/{job.id}/cancel",
                                    headers=VIEWER)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "cancelled")

    def test_cancelled_job_serializes_correctly(self) -> None:
        self.assertEqual(self._prime().status_code, 200)
        job = _enqueue(CASE_ID, f"serial-rev-{uuid.uuid4().hex[:8]}")
        cancel = self.client.post(f"/api/jobs/{job.id}/cancel",
                                  headers=REVIEWER)
        self.assertEqual(cancel.status_code, 200)
        response = self.client.get(f"/api/cases/{CASE_ID}/jobs",
                                   headers=REVIEWER)
        self.assertEqual(response.status_code, 200)
        row = next(r for r in response.json() if r["job_id"] == job.id)
        self.assertEqual(row["revision_id"], job.revision_id)
        self.assertEqual(row["state"], "cancelled")
        self.assertIsInstance(row["attempt_count"], int)
        self.assertIsInstance(row["fencing_token"], int)
        self.assertIsNone(row["lease_owner"])
        self.assertIsNone(row["last_error"])
        self.assertEqual(set(row.keys()), EXPECTED_KEYS)


if __name__ == "__main__":
    unittest.main()
