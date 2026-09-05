"""Job queue: leases, fencing tokens, retry, offline fallback."""

from __future__ import annotations

import unittest

from src.agent import JOB_STORE, build_agent_graph
from src.covenant import build_demo_workflow
from src.platform.jobqueue import (
    JobConflictError,
    MemoryJobStore,
    StaleLeaseError,
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
        job = self.store.enqueue("case-a", "rev-1", max_attempts=2)
        leased = self.store.lease("worker-1")
        retry = self.store.fail(job.id, leased.fencing_token, "boom")
        self.assertEqual(retry.state, "queued")
        leased2 = self.store.lease("worker-1")
        final = self.store.fail(job.id, leased2.fencing_token, "boom again")
        self.assertEqual(final.state, "failed")

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
        import os
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("SUPABASE_DB_URL", None)
        store = job_store_from_env()
        self.assertIsInstance(store, MemoryJobStore)

    def test_agent_graph_compiles_with_durable_checkpointer(self):
        graph = build_agent_graph(build_demo_workflow())
        self.assertIsNotNone(graph)
        cp = durable_checkpointer()
        self.assertIsNotNone(cp)
        self.assertIsNotNone(JOB_STORE)


if __name__ == "__main__":
    unittest.main()
