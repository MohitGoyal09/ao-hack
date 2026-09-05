"""Domain-event feed route ``GET /api/cases/{case_id}/events`` (offline scope)."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

import main
from main import app

CASE_ID = "aurora-net-leverage"
OUTSIDER = {"Authorization": "Bearer mallory:treasury_reviewer:org-nobody"}
EXPECTED_KEYS = {"sequence", "event_type", "revision_id", "run_id", "payload",
                 "created_at"}


class EventsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.repo = main.revision_repository
        # Other modules may already have primed this case under their org;
        # join that org instead of fighting over it (same-org users are
        # auto-provisioned offline).
        try:
            org = self.repo.get_case_org(CASE_ID)
        except Exception:
            org = "demo-org"
        self.headers = {"Authorization": f"Bearer gina:treasury_reviewer:{org}"}
        self.assertEqual(self._get().status_code, 200)  # primes rev-1 + REVISION_CREATED
        self.org = self.repo.get_case_org(CASE_ID)

    def _get(self, query: str = "", headers: dict | None = None):
        return self.client.get(f"/api/cases/{CASE_ID}/events{query}",
                               headers=self.headers if headers is None else headers)

    def _append(self, event_type: str, **payload):
        head = self.repo.current(CASE_ID).revision_id
        return self.repo.append_event(CASE_ID, self.org, head, "job-x",
                                      event_type, payload)

    def test_unauthenticated_returns_401(self) -> None:
        self.assertEqual(self._get(headers={}).status_code, 401)

    def test_unknown_case_returns_404(self) -> None:
        response = self.client.get("/api/cases/not-a-case/events",
                                   headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_foreign_org_gets_404_without_leaking(self) -> None:
        response = self._get(headers=OUTSIDER)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(self.org, response.text)
        self.assertNotIn("REVISION_CREATED", response.text)

    def test_events_ordered_by_sequence_with_public_shape(self) -> None:
        started = self._append("RUN_STARTED", job_id="job-x")
        calc = self._append("CALCULATION_COMPLETED", job_id="job-x", ratio="2.86")
        body = self._get().json()
        seqs = [row["sequence"] for row in body]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(set(seqs)), len(seqs))
        self.assertEqual(body[0]["event_type"], "REVISION_CREATED")
        for row in body:
            self.assertEqual(set(row), EXPECTED_KEYS)
        mine = [row for row in body
                if row["sequence"] in (started["sequence"], calc["sequence"])]
        self.assertEqual([row["event_type"] for row in mine],
                         ["RUN_STARTED", "CALCULATION_COMPLETED"])
        self.assertEqual(mine[0]["run_id"], "job-x")
        self.assertEqual(mine[1]["payload"], {"job_id": "job-x", "ratio": "2.86"})
        self.assertIsInstance(mine[0]["created_at"], str)

    def test_after_sequence_cursor_and_limit(self) -> None:
        before = self._get().json()[-1]["sequence"]
        first = self._append("RUN_STARTED", job_id="job-x")
        second = self._append("RUN_COMPLETED", job_id="job-x", status="completed")
        body = self._get(f"?after_sequence={before}").json()
        self.assertEqual([row["sequence"] for row in body],
                         [first["sequence"], second["sequence"]])
        capped = self._get(f"?after_sequence={before}&limit=1").json()
        self.assertEqual([row["sequence"] for row in capped], [first["sequence"]])
        self.assertEqual(self._get(f"?after_sequence={second['sequence']}").json(), [])


if __name__ == "__main__":
    unittest.main()
