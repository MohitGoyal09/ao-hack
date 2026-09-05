"""Public HTTP health seams for durability readiness."""

import unittest

from fastapi.testclient import TestClient

from main import create_app
from src.platform.jobqueue import DurabilityComponentStatus, DurabilityStatus


def offline_status() -> DurabilityStatus:
    return DurabilityStatus(
        queue=DurabilityComponentStatus.offline("queue"),
        checkpoint=DurabilityComponentStatus.offline("checkpoint"),
    )


def unavailable_status() -> DurabilityStatus:
    return DurabilityStatus(
        queue=DurabilityComponentStatus.failed("queue"),
        checkpoint=DurabilityComponentStatus.failed("checkpoint"),
    )


class ReadinessApiTests(unittest.TestCase):

    def test_liveness_is_available_without_durability(self) -> None:
        response = TestClient(create_app(durability_status=unavailable_status())).get("/health/live")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "live")

    def test_offline_mode_is_explicitly_ready_but_degraded(self) -> None:
        response = TestClient(create_app(durability_status=offline_status())).get("/health/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")
        self.assertEqual(response.json()["durability"]["mode"], "offline-memory")

    def test_configured_durability_failure_is_redacted_and_unready(self) -> None:
        response = TestClient(create_app(durability_status=unavailable_status())).get("/health/ready")

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "unready")
        self.assertTrue(body["durability"]["queue"]["configured"])
        self.assertFalse(body["durability"]["queue"]["verified"])
        self.assertNotIn("postgresql://", str(body))
        self.assertNotIn("password", str(body).lower())

    def test_configured_durability_failure_rejects_business_traffic(self) -> None:
        response = TestClient(create_app(durability_status=unavailable_status())).get("/api/demo-cases")

        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
