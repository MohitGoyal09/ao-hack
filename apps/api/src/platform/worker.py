"""Lease-guarded worker runtime for revision-run jobs.

Owns fencing-token discipline: a worker only publishes with the token it was
granted. Any StaleLeaseError surfaces as "stale" without further publishing.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.platform.jobqueue import StaleLeaseError

from src.covenant.pipeline import (
    CasePipeline,
    PermanentRunError,
    PipelineError,
    TransientRunError,
)

logger = logging.getLogger(__name__)


class Worker:
    """Lease one job, run the pipeline, publish with the fencing token."""

    def __init__(
        self,
        job_store: Any,
        pipeline: Any,
        worker_id: str,
        lease_seconds: int = 60,
    ) -> None:
        self._store = job_store
        self._pipeline = pipeline
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds

    def run_once(self) -> str:
        job = self._store.lease(self._worker_id, self._lease_seconds)
        if job is None:
            return "idle"
        job_id = job.id
        token = job.fencing_token
        logger.info("worker leased job job_id=%s worker_id=%s", job_id, self._worker_id)

        # --- begin phase: same retry/terminal mapping as run phase ---
        try:
            self._pipeline.begin(job)
        except StaleLeaseError:
            logger.info("worker stale job_id=%s worker_id=%s", job_id, self._worker_id)
            return "stale"
        except PermanentRunError as error:
            logger.info("worker permanent job_id=%s worker_id=%s", job_id, self._worker_id)
            return self._publish_cancel(job_id, token, type(error).__name__)
        except TransientRunError as error:
            logger.info("worker retrying job_id=%s worker_id=%s", job_id, self._worker_id)
            return self._publish_fail(job_id, token, type(error).__name__)
        except Exception as error:  # unexpected -> retry
            logger.info("worker retrying job_id=%s worker_id=%s", job_id, self._worker_id)
            return self._publish_fail(job_id, token, type(error).__name__)

        # --- run phase with heartbeat progress ---
        def _on_progress() -> None:
            self._store.heartbeat(job_id, token, self._lease_seconds)

        try:
            result = self._pipeline.run(job, on_progress=_on_progress)
        except StaleLeaseError:
            logger.info("worker stale job_id=%s worker_id=%s", job_id, self._worker_id)
            return "stale"
        except PermanentRunError as error:
            logger.info("worker permanent job_id=%s worker_id=%s", job_id, self._worker_id)
            return self._publish_cancel(job_id, token, type(error).__name__)
        except TransientRunError as error:
            logger.info("worker retrying job_id=%s worker_id=%s", job_id, self._worker_id)
            return self._publish_fail(job_id, token, type(error).__name__)
        except Exception as error:  # unexpected -> retry
            logger.info("worker retrying job_id=%s worker_id=%s", job_id, self._worker_id)
            return self._publish_fail(job_id, token, type(error).__name__)

        current = self._store.get(job_id)
        if current is None:
            logger.info("worker stale job_id=%s worker_id=%s", job_id, self._worker_id)
            return "stale"
        if current.state == "cancelled":
            logger.info(
                "worker cancelled job_id=%s worker_id=%s", job_id, self._worker_id
            )
            return "cancelled"
        try:
            self._store.complete(job_id, token, result)
        except StaleLeaseError:
            logger.info("worker stale job_id=%s worker_id=%s", job_id, self._worker_id)
            return "stale"
        logger.info("worker completed job_id=%s worker_id=%s", job_id, self._worker_id)
        return "completed"

    def _publish_fail(self, job_id: str, token: int, error_kind: str) -> str:
        current = self._store.get(job_id)
        if current is not None and current.state == "cancelled":
            logger.info(
                "worker cancelled job_id=%s worker_id=%s", job_id, self._worker_id
            )
            return "cancelled"
        try:
            self._store.fail(job_id, token, error_kind)
        except StaleLeaseError:
            logger.info("worker stale job_id=%s worker_id=%s", job_id, self._worker_id)
            return "stale"
        updated = self._store.get(job_id)
        if updated is not None and updated.state == "failed":
            logger.info("worker failed job_id=%s worker_id=%s", job_id, self._worker_id)
            return "failed"
        logger.info("worker retrying job_id=%s worker_id=%s", job_id, self._worker_id)
        return "retrying"

    def _publish_cancel(self, job_id: str, token: int, _error_kind: str) -> str:
        current = self._store.get(job_id)
        if current is None:
            logger.info("worker stale job_id=%s worker_id=%s", job_id, self._worker_id)
            return "stale"
        if current.state == "cancelled":
            logger.info(
                "worker cancelled job_id=%s worker_id=%s", job_id, self._worker_id
            )
            return "cancelled"
        # Fencing: a stale worker must not cancel a job that was re-leased
        # to someone else after a lease-expiry takeover.
        if current.fencing_token != token:
            logger.info("worker stale job_id=%s worker_id=%s", job_id, self._worker_id)
            return "stale"
        try:
            self._store.cancel(job_id)
        except StaleLeaseError:
            logger.info("worker stale job_id=%s worker_id=%s", job_id, self._worker_id)
            return "stale"
        logger.info("worker failed job_id=%s worker_id=%s", job_id, self._worker_id)
        return "failed"

    def run_forever(
        self,
        poll_interval_seconds: float = 5,
        stop_after_idle: int | None = None,
    ) -> None:
        idle_count = 0
        while True:
            outcome = self.run_once()
            if outcome == "idle":
                idle_count += 1
            else:
                idle_count = 0
            if stop_after_idle is not None and idle_count >= stop_after_idle:
                return
            if poll_interval_seconds and poll_interval_seconds > 0:
                time.sleep(poll_interval_seconds)


def main() -> None:
    """Entry point; all env/DB imports stay lazy so module import is side-effect free."""
    import os
    import uuid

    from src.platform.jobqueue import configured_database_url, job_store_from_env

    worker_id = os.getenv("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
    try:
        lease_seconds = int(os.getenv("WORKER_LEASE_SECONDS", "60"))
    except ValueError:
        lease_seconds = 60
    try:
        poll_interval = float(os.getenv("WORKER_POLL_INTERVAL", "5"))
    except ValueError:
        poll_interval = 5

    store = job_store_from_env()
    from src.covenant.pipeline import CasePipeline as _Pipeline

    from src.platform.storage import storage_adapter_from_env

    storage = storage_adapter_from_env(None)
    pipeline = _Pipeline(configured_database_url(), storage)
    worker = Worker(store, pipeline, worker_id=worker_id, lease_seconds=lease_seconds)
    worker.run_forever(poll_interval_seconds=poll_interval)


if __name__ == "__main__":
    main()
