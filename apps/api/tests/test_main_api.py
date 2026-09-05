import unittest

from fastapi.testclient import TestClient

from main import app


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


if __name__ == "__main__":
    unittest.main()
