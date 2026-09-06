"""Lease-guarded worker runtime for revision-run jobs.

Owns fencing-token discipline: a worker only publishes with the token it was
granted. Any StaleLeaseError surfaces as "stale" without further publishing.
"""

from __future__ import annotations

import logging
import threading
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
        outcome = self._process(job)
        # Every terminal outcome routes through here, so the revision's
        # run_state can never be left at 'running' by a failed or cancelled job.
        if outcome in ("failed", "cancelled"):
            self._mark_revision(job, outcome)
        return outcome

    def _process(self, job: Any) -> str:
        job_id = job.id
        token = job.fencing_token
        logger.info("worker leased job job_id=%s worker_id=%s", job_id, self._worker_id)

        # --- begin phase: same retry/terminal mapping as run phase ---
        try:
            if job.attempt_count > 1:
                # RUN_STARTED is emitted once per job (by begin); retries only annotate.
                self._emit(job, "RUN_RETRIED",
                           {"job_id": job_id, "attempt": job.attempt_count,
                            "last_error": job.last_error})
            else:
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

    def _mark_revision(self, job: Any, state: str) -> None:
        """Best effort: terminal job outcome -> case_revisions.run_state via the
        pipeline's public ``set_run_state(job, state)`` hook (absent on test fakes)."""
        setter = getattr(self._pipeline, "set_run_state", None)
        if setter is None:
            return
        try:
            setter(job, state)
        except Exception:
            logger.warning("worker could not set run_state=%s job_id=%s",
                           state, job.id, exc_info=True)

    # ponytail: RUN_RETRIED goes through CasePipeline's private event sink via
    # getattr (no public hook yet); promote to one if a second pipeline appears.
    def _emit(self, job: Any, event_type: str, summary: dict) -> None:
        """Best effort: append a RUN_* domain event through the pipeline's sink."""
        append = getattr(self._pipeline, "_append_event", None)
        resolve = getattr(self._pipeline, "_resolve_org", None)
        if append is None or resolve is None:
            return
        try:
            append(job.case_id, resolve(job), job.revision_id, job.id,
                   event_type, dict(summary))
        except Exception:
            logger.warning("worker could not append %s job_id=%s",
                           event_type, job.id, exc_info=True)

    def run_forever(
        self,
        poll_interval_seconds: float = 5,
        stop_after_idle: int | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        """Poll until ``stop_event`` is set (or ``stop_after_idle`` idle polls)."""
        stop_event = stop_event or threading.Event()
        idle_count = 0
        while not stop_event.is_set():
            outcome = self.run_once()
            if outcome == "idle":
                idle_count += 1
            else:
                idle_count = 0
            if stop_after_idle is not None and idle_count >= stop_after_idle:
                return
            if poll_interval_seconds and poll_interval_seconds > 0:
                if stop_event.wait(poll_interval_seconds):
                    return


def main() -> None:
    """Entry point; all env/DB imports stay lazy so module import is side-effect free."""
    import os
    import uuid

    from dotenv import load_dotenv

    load_dotenv()  # same root .env main.py loads; never overrides exported vars
    logging.basicConfig(level=os.getenv("WORKER_LOG_LEVEL", "INFO"))

    from src.platform.jobqueue import configured_database_url, job_store_from_env
    from src.platform.supabase import SupabasePlatform

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

    # The API uploads to Supabase Storage; read from the same bucket.
    platform = SupabasePlatform.from_env()
    storage = storage_adapter_from_env(
        platform._client if platform.enabled else None,  # noqa: SLF001
        platform._bucket,  # noqa: SLF001
    )
    pipeline = _Pipeline(configured_database_url(), storage)
    # Recalculation jobs on revisions without uploaded documents recompute
    # from the authoritative fixture case; derived case ids fall back to
    # their catalog template.
    from src.covenant import UnknownCaseError, build_demo_workflow

    _demo = build_demo_workflow()
    try:
        from src.covenant.revision_repository import PostgresRevisionRepository

        _pg = PostgresRevisionRepository(configured_database_url()) \
            if configured_database_url() else None
    except Exception:
        _pg = None

    def _case_provider(case_id: str):
        try:
            return _demo._repository.get_case(case_id)  # noqa: SLF001
        except UnknownCaseError:
            if _pg is not None:
                template = _pg.case_template(case_id)
                if template is not None:
                    return _demo._repository.get_case(template)  # noqa: SLF001
            raise

    pipeline.case_provider = _case_provider
    worker = Worker(store, pipeline, worker_id=worker_id, lease_seconds=lease_seconds)
    worker.run_forever(poll_interval_seconds=poll_interval)


if __name__ == "__main__":
    main()
