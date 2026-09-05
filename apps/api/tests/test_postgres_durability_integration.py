"""Opt-in integration coverage for existing shared Postgres durability schema.

This test never invokes ``PostgresSaver.setup`` and never creates or drops
schema. Point TEST_DATABASE_URL at an isolated, pre-provisioned test database.
"""

from __future__ import annotations

import os
import uuid
import unittest

from langgraph.checkpoint.base import empty_checkpoint

from src.platform.jobqueue import PostgresJobStore, build_durability_runtime


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is not configured")
class PostgresDurabilityIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dsn = os.environ["TEST_DATABASE_URL"]
        self.runtime = build_durability_runtime(self.dsn)
        if not self.runtime.status.ready:
            self.skipTest("pre-provisioned queue or checkpoint schema is unavailable")

    def tearDown(self) -> None:
        self.runtime.close()

    def test_queue_and_checkpoint_survive_reconstruction(self) -> None:
        """Both durable public seams remain readable from a new connection."""
        job = self.runtime.job_store.enqueue(
            f"integration-case-{uuid.uuid4().hex}", "integration-revision"
        )
        reconstructed_store = PostgresJobStore(self.dsn)
        self.assertEqual(reconstructed_store.get(job.id).id, job.id)

        thread_id = f"integration-thread-{uuid.uuid4().hex}"
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = {"proof": "durable"}
        self.runtime.checkpointer.put(config, checkpoint, {}, {"proof": 1})

        reconstructed = build_durability_runtime(self.dsn)
        try:
            restored = reconstructed.checkpointer.get_tuple(
                {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            )
        finally:
            reconstructed.close()
        self.assertIsNotNone(restored)
        self.assertEqual(restored.checkpoint["channel_values"]["proof"], "durable")


if __name__ == "__main__":
    unittest.main()
