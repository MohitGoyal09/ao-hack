"""Worker runtime tests: leases, fencing, cancel, retry mapping."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.platform.jobqueue import MemoryJobStore, StaleLeaseError
from src.platform.worker import (
    PermanentRunError,
    TransientRunError,
    Worker,
)


def _result(revision_id="rev-1"):
    return {
        "status": "completed",
        "revision_id": revision_id,
        "artifacts": [],
        "calculation": {},
        "error": None,
    }


class HappyPipeline:
    def __init__(self, result=None, call_progress=True):
        self._result = result or _result()
        self.begin_calls: list[str] = []
        self.run_calls: list[str] = []
        self.call_progress = call_progress

    def begin(self, job):
        self.begin_calls.append(job.id)

    def run(self, job, on_progress):
        self.run_calls.append(job.id)
        if self.call_progress:
            on_progress()
        return self._result


class RecordingStore(MemoryJobStore):
    def __init__(self):
        super().__init__()
        self.heartbeat_calls: list[tuple] = []

    def heartbeat(self, job_id, fencing_token, lease_seconds=60):
        self.heartbeat_calls.append((job_id, fencing_token, lease_seconds))
        return super().heartbeat(job_id, fencing_token, lease_seconds)


def _expire(store, job_id):
    stored = store.get(job_id)
    assert stored is not None
    stored.lease_expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)


class WorkerTest(unittest.TestCase):
    def test_happy_path_completes_with_result(self):
        store = MemoryJobStore()
        job = store.enqueue("case-a", "rev-1")
        expected = _result("rev-1")
        worker = Worker(store, HappyPipeline(result=expected), "worker-1")
        outcome = worker.run_once()
        self.assertEqual(outcome, "completed")
        done = store.get(job.id)
        assert done is not None
        self.assertEqual(done.state, "completed")
        self.assertEqual(done.payload, expected)

    def test_expired_lease_takeover_first_publish_stale(self):
        store = MemoryJobStore()
        job = store.enqueue("case-a", "rev-1")

        class TakeoverPipeline:
            def begin(self, j):
                pass

            def run(self, j, on_progress):
                _expire(store, j.id)
                second = store.lease("worker-2")
                assert second is not None
                return _result()

        worker1 = Worker(store, TakeoverPipeline(), "worker-1")
        outcome = worker1.run_once()
        self.assertEqual(outcome, "stale")
        current = store.get(job.id)
        assert current is not None
        self.assertEqual(current.state, "running")
        self.assertEqual(current.lease_owner, "worker-2")

    def test_cancelled_job_dropped_not_published(self):
        store = MemoryJobStore()
        job = store.enqueue("case-a", "rev-1")
        expected = _result()

        class CancellingPipeline:
            def begin(self, j):
                pass

            def run(self, j, on_progress):
                store.cancel(j.id)
                return expected

        worker = Worker(store, CancellingPipeline(), "worker-1")
        outcome = worker.run_once()
        self.assertEqual(outcome, "cancelled")
        current = store.get(job.id)
        assert current is not None
        self.assertEqual(current.state, "cancelled")
        self.assertNotEqual(current.payload, expected)

    def test_transient_error_retries_then_succeeds(self):
        store = MemoryJobStore()
        job = store.enqueue("case-a", "rev-1")

        class FlakyPipeline:
            def __init__(self):
                self.calls = 0

            def begin(self, j):
                pass

            def run(self, j, on_progress):
                self.calls += 1
                if self.calls == 1:
                    raise TransientRunError("boom")
                return _result()

        pipeline = FlakyPipeline()
        worker = Worker(store, pipeline, "worker-1")
        first = worker.run_once()
        self.assertEqual(first, "retrying")
        mid = store.get(job.id)
        assert mid is not None
        self.assertEqual(mid.state, "queued")
        second = worker.run_once()
        self.assertEqual(second, "completed")
        done = store.get(job.id)
        assert done is not None
        self.assertEqual(done.state, "completed")

    def test_permanent_error_cancels_without_retry(self):
        store = MemoryJobStore()
        job = store.enqueue("case-a", "rev-1")

        class BadPipeline:
            def begin(self, j):
                pass

            def run(self, j, on_progress):
                raise PermanentRunError("bad input")

        worker = Worker(store, BadPipeline(), "worker-1")
        outcome = worker.run_once()
        self.assertEqual(outcome, "failed")
        current = store.get(job.id)
        assert current is not None
        self.assertEqual(current.state, "cancelled")
        # Cancelled jobs are never re-leased.
        self.assertEqual(worker.run_once(), "idle")

    def test_unexpected_exception_retries(self):
        store = MemoryJobStore()
        job = store.enqueue("case-a", "rev-1")

        class ExplodingPipeline:
            def begin(self, j):
                pass

            def run(self, j, on_progress):
                raise ValueError("unexpected")

        worker = Worker(store, ExplodingPipeline(), "worker-1")
        outcome = worker.run_once()
        self.assertEqual(outcome, "retrying")
        current = store.get(job.id)
        assert current is not None
        self.assertEqual(current.state, "queued")

    def test_heartbeat_uses_granted_fencing_token(self):
        store = RecordingStore()
        job = store.enqueue("case-a", "rev-1")
        worker = Worker(store, HappyPipeline(), "worker-1", lease_seconds=60)
        outcome = worker.run_once()
        self.assertEqual(outcome, "completed")
        self.assertEqual(len(store.heartbeat_calls), 1)
        hb_job_id, hb_token, hb_lease = store.heartbeat_calls[0]
        self.assertEqual(hb_job_id, job.id)
        current = store.get(job.id)
        assert current is not None
        self.assertEqual(hb_token, current.fencing_token)
        self.assertEqual(hb_lease, 60)

    def test_stale_heartbeat_returns_stale(self):
        store = MemoryJobStore()
        job = store.enqueue("case-a", "rev-1")

        class StaleHeartbeatPipeline:
            def begin(self, j):
                pass

            def run(self, j, on_progress):
                _expire(store, j.id)
                taken = store.lease("worker-2")
                assert taken is not None
                with self.assertRaises(StaleLeaseError):
                    on_progress()
                # Return normally; the later complete must also go stale.
                return _result()

        worker = Worker(store, StaleHeartbeatPipeline(), "worker-1")
        outcome = worker.run_once()
        self.assertEqual(outcome, "stale")


if __name__ == "__main__":
    unittest.main()
