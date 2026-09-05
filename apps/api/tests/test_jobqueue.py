"""Job queue: leases, fencing tokens, retry, offline fallback."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.agent import build_agent_graph
from src.covenant import build_demo_workflow
from src.platform.jobqueue import (
    DurabilityConfigurationError,
    JobConflictError,
    MemoryJobStore,
    StaleLeaseError,
    build_durability_runtime,
    durable_checkpointer,
    job_store_from_env,
)


class JobQueueTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryJobStore()

    def test_enqueue_and_single_active_revision(self):
        self.store.enqueue("case-a", "rev-1")
        with self.assertRaises(JobConflictError):
            self.store.enqueue("case-a", "rev-1")

    def test_lease_bumps_attempt_and_fencing_token(self):
        job = self.store.enqueue("case-a", "rev-1")
        leased = self.store.lease("worker-1")
        self.assertIsNotNone(leased)
        self.assertEqual(leased.state, "running")
        self.assertEqual(leased.attempt_count, 1)
        self.assertEqual(leased.fencing_token, 1)

    def test_stale_worker_cannot_publish(self):
        job = self.store.enqueue("case-a", "rev-1")
        first = self.store.lease("worker-1")
        token1 = first.fencing_token
        # Simulate lease expiry + re-lease to worker-2 by expiring directly.
        stored = self.store.get(job.id)
        assert stored is not None
        from datetime import datetime, timezone
        stored.lease_expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        second = self.store.lease("worker-2")
        self.assertEqual(second.lease_owner, "worker-2")
        with self.assertRaises(StaleLeaseError):
            self.store.complete(job.id, token1, {"ok": True})
        done = self.store.complete(job.id, second.fencing_token, {"ok": True})
        self.assertEqual(done.state, "completed")

    def test_fail_retries_until_max_attempts(self):
        store = MemoryJobStore(retry_backoff_seconds=0)
        job = store.enqueue("case-a", "rev-1", max_attempts=2)
        leased = store.lease("worker-1")
        retry = store.fail(job.id, leased.fencing_token, "boom")
        self.assertEqual(retry.state, "queued")
        leased2 = store.lease("worker-1")
        final = store.fail(job.id, leased2.fencing_token, "boom again")
        self.assertEqual(final.state, "failed")
        self.assertIsNone(final.lease_expires_at)

    def test_fail_applies_retry_backoff_before_release(self):
        from datetime import datetime, timezone

        job = self.store.enqueue("case-a", "rev-1")
        leased = self.store.lease("worker-1")
        retry = self.store.fail(job.id, leased.fencing_token, "boom")
        self.assertEqual(retry.state, "queued")
        self.assertGreater(retry.lease_expires_at, datetime.now(timezone.utc))
        # Default backoff is attempt_count * 10s; not leasable until it passes.
        self.assertIsNone(self.store.lease("worker-1"))
        retry.lease_expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(self.store.lease("worker-1").attempt_count, 2)

    def test_heartbeat_rejects_stale_token(self):
        job = self.store.enqueue("case-a", "rev-1")
        leased = self.store.lease("worker-1")
        with self.assertRaises(StaleLeaseError):
            self.store.heartbeat(job.id, leased.fencing_token + 99)
        ok = self.store.heartbeat(job.id, leased.fencing_token)
        self.assertEqual(ok.fencing_token, leased.fencing_token)

    def test_cancel_is_terminal(self):
        job = self.store.enqueue("case-a", "rev-1")
        cancelled = self.store.cancel(job.id)
        self.assertEqual(cancelled.state, "cancelled")

    def test_offline_fallback_without_database_url(self):
        with patch.dict("os.environ", {}, clear=True):
            store = job_store_from_env()
        self.assertIsInstance(store, MemoryJobStore)

    def test_configured_database_failure_never_downgrades_to_memory(self):
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://unavailable"}, clear=True):
            with patch("src.platform.jobqueue.PostgresJobStore", side_effect=OSError("offline")):
                with self.assertRaises(DurabilityConfigurationError):
                    job_store_from_env()

    def test_configured_checkpoint_failure_never_downgrades_to_memory(self):
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://unavailable"}, clear=True):
            with patch("langgraph.checkpoint.postgres.PostgresSaver.from_conn_string",
                       side_effect=OSError("offline")):
                runtime = build_durability_runtime()
        self.assertTrue(runtime.status.checkpoint.configured)
        self.assertFalse(runtime.status.checkpoint.verified)
        self.assertIsNone(runtime.checkpointer)

    def test_postgres_checkpointer_context_stays_open_without_schema_setup(self):
        """The application owns the context manager for as long as the graph uses it."""
        saver = MagicMock()
        context = MagicMock()
        context.__enter__.return_value = saver
        store = MagicMock()
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://configured"}, clear=True):
            with patch("src.platform.jobqueue.PostgresJobStore", return_value=store):
                with patch("langgraph.checkpoint.postgres.PostgresSaver.from_conn_string", return_value=context):
                    runtime = build_durability_runtime()
        saver.setup.assert_not_called()
        saver.get_tuple.assert_called_once()
        context.__exit__.assert_not_called()
        runtime.close()
        context.__exit__.assert_called_once()

    def test_postgres_saver_async_methods_delegate_to_sync(self):
        """The AG-UI agent runs the graph async; the sync saver must not raise."""
        import asyncio

        from src.platform.jobqueue import _postgres_saver_class

        saver = _postgres_saver_class()(MagicMock())
        saver.get_tuple = MagicMock(return_value="tuple")
        saver.put = MagicMock(return_value={"configurable": {}})
        saver.put_writes = MagicMock()
        saver.list = MagicMock(return_value=iter(["a", "b"]))

        async def exercise():
            got = await saver.aget_tuple({"configurable": {"thread_id": "t"}})
            put = await saver.aput({"configurable": {}}, {}, {}, {})
            await saver.aput_writes({"configurable": {}}, [], "task")
            listed = [item async for item in saver.alist(None, limit=2)]
            return got, put, listed

        got, put, listed = asyncio.run(exercise())
        self.assertEqual(got, "tuple")
        self.assertEqual(put, {"configurable": {}})
        self.assertEqual(listed, ["a", "b"])
        saver.put_writes.assert_called_once()

    def test_agent_graph_compiles_with_durable_checkpointer(self):
        with patch.dict("os.environ", {}, clear=True):
            graph = build_agent_graph(
                build_demo_workflow(), checkpointer=durable_checkpointer()
            )
        self.assertIsNotNone(graph)
        with patch.dict("os.environ", {}, clear=True):
            cp = durable_checkpointer()
        self.assertIsNotNone(cp)


if __name__ == "__main__":
    unittest.main()
