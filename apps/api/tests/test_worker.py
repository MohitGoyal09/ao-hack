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
        store = MemoryJobStore(retry_backoff_seconds=0)
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


class RevisionAwarePipeline(HappyPipeline):
    """Fake exposing the CasePipeline private hooks the worker calls."""

    def __init__(self, fail_times=0, permanent=False):
        super().__init__()
        self.fail_times = fail_times
        self.permanent = permanent
        self.run_states: list[tuple] = []
        self.events: list[tuple] = []

    def _resolve_org(self, job):
        return "org-1"

    def set_run_state(self, job, state):
        self.run_states.append(("org-1", job.case_id, job.revision_id, state))

    def _append_event(self, case_id, org, revision_id, run_id, event_type, summary):
        self.events.append((event_type, dict(summary)))

    def run(self, job, on_progress):
        self.run_calls.append(job.id)
        if self.permanent:
            raise PermanentRunError("bad input")
        if len(self.run_calls) <= self.fail_times:
            raise TransientRunError("boom")
        return self._result


class WorkerRevisionStateTest(unittest.TestCase):
    def test_retry_emits_run_retried_and_begins_once(self):
        store = MemoryJobStore(retry_backoff_seconds=0)
        store.enqueue("case-a", "rev-1")
        pipeline = RevisionAwarePipeline(fail_times=1)
        worker = Worker(store, pipeline, "worker-1")
        self.assertEqual(worker.run_once(), "retrying")
        self.assertEqual(worker.run_once(), "completed")
        self.assertEqual(len(pipeline.begin_calls), 1)
        self.assertEqual([e[0] for e in pipeline.events], ["RUN_RETRIED"])
        self.assertEqual(pipeline.events[0][1]["attempt"], 2)
        self.assertEqual(pipeline.run_states, [])

    def test_terminal_failure_marks_revision_failed(self):
        store = MemoryJobStore(retry_backoff_seconds=0)
        store.enqueue("case-a", "rev-1", max_attempts=2)
        pipeline = RevisionAwarePipeline(fail_times=5)
        worker = Worker(store, pipeline, "worker-1")
        self.assertEqual(worker.run_once(), "retrying")
        self.assertEqual(worker.run_once(), "failed")
        self.assertEqual(pipeline.run_states, [("org-1", "case-a", "rev-1", "failed")])

    def test_permanent_error_marks_revision_failed(self):
        store = MemoryJobStore()
        store.enqueue("case-a", "rev-1")
        pipeline = RevisionAwarePipeline(permanent=True)
        self.assertEqual(Worker(store, pipeline, "worker-1").run_once(), "failed")
        self.assertEqual(pipeline.run_states[-1][3], "failed")

    def test_cancel_during_run_marks_revision_cancelled(self):
        store = MemoryJobStore()
        job = store.enqueue("case-a", "rev-1")
        pipeline = RevisionAwarePipeline()
        original_run = pipeline.run

        def cancelling_run(j, on_progress):
            store.cancel(j.id)
            return original_run(j, on_progress)

        pipeline.run = cancelling_run
        self.assertEqual(Worker(store, pipeline, "worker-1").run_once(), "cancelled")
        self.assertEqual(store.get(job.id).state, "cancelled")
        self.assertEqual(pipeline.run_states[-1][3], "cancelled")

    def test_run_forever_stops_on_event(self):
        import threading

        store = MemoryJobStore()
        store.enqueue("case-a", "rev-1")
        pipeline = HappyPipeline()
        stop = threading.Event()
        thread = threading.Thread(
            target=Worker(store, pipeline, "worker-1").run_forever,
            kwargs={"poll_interval_seconds": 0.01, "stop_event": stop},
            daemon=True,
        )
        thread.start()
        deadline = 50
        while not pipeline.run_calls and deadline:
            stop.wait(0.02)
            deadline -= 1
        stop.set()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(pipeline.run_calls), 1)


if __name__ == "__main__":
    unittest.main()
