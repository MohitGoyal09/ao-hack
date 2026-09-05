"""AG-UI endpoint smoke test (offline deterministic graph, no LLM key)."""

from __future__ import annotations

import json
import unittest
import uuid

from fastapi.testclient import TestClient

from main import app


def _run_agent_input(text: str) -> dict:
    return {
        "threadId": f"thread-{uuid.uuid4().hex[:8]}",
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "state": {},
        "messages": [{"id": "m-1", "role": "user", "content": text}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


def _events(response) -> list[dict]:
    return [
        json.loads(line[len("data:"):])
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]


def _assistant_text(events: list[dict]) -> str:
    """The offline graph returns one AIMessage per node (no token stream); the
    reply is carried by the final MESSAGES_SNAPSHOT."""
    snapshots = [e for e in events if e["type"] == "MESSAGES_SNAPSHOT"]
    assert snapshots, "no MESSAGES_SNAPSHOT in stream"
    return "\n".join(
        str(m.get("content", "")) for m in snapshots[-1]["messages"]
        if m.get("role") == "assistant"
    )


class AgUiEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_ag_ui_health_is_mounted(self) -> None:
        response = self.client.get("/ag-ui/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["agent"]["name"], "covenant_agent")

    def test_list_cases_streams_started_to_finished(self) -> None:
        response = self.client.post(
            "/ag-ui", json=_run_agent_input("list the covenant cases")
        )
        self.assertEqual(response.status_code, 200, response.text)
        events = _events(response)
        types = [event["type"] for event in events]
        self.assertEqual(types[0], "RUN_STARTED")
        self.assertEqual(types[-1], "RUN_FINISHED")
        self.assertNotIn("RUN_ERROR", types)
        self.assertIn("aurora-net-leverage", _assistant_text(events))

    def test_run_case_reply_contains_ratio(self) -> None:
        response = self.client.post(
            "/ag-ui", json=_run_agent_input("run aurora-net-leverage")
        )
        self.assertEqual(response.status_code, 200, response.text)
        events = _events(response)
        types = [event["type"] for event in events]
        self.assertNotIn("RUN_ERROR", types)
        self.assertEqual(types[-1], "RUN_FINISHED")
        text = _assistant_text(events)
        self.assertIn("ratio is", text)
        self.assertRegex(text, r"\d+\.\d{2}x")


if __name__ == "__main__":
    unittest.main()
