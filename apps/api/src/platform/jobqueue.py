"""Durable revision-run job queue with leases and fencing tokens.

Online path: Postgres table ``public.revision_run_jobs`` via ``DATABASE_URL``
(psycopg). Offline path (no database configuration): an in-process store with
identical semantics so the test suite runs offline. A configured durable path
must initialize successfully; it never silently downgrades to memory.

Fencing: every lease grant bumps ``fencing_token``. ``complete``/``fail``
require the caller to present the token it was granted; a worker that lost
its lease (token mismatch) raises :class:`StaleLeaseError` and cannot publish.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

ACTIVE_STATES = ("queued", "running", "waiting_review")
TERMINAL_STATES = ("completed", "failed", "cancelled")


class StaleLeaseError(RuntimeError):
    pass


class JobConflictError(RuntimeError):
    pass


class DurabilityConfigurationError(RuntimeError):
    """A configured durable dependency could not be initialized safely."""


@dataclass(frozen=True)
class DurabilityComponentStatus:
    """Public, redacted status for one durable dependency."""

    component: Literal["queue", "checkpoint"]
    configured: bool
    verified: bool
    mode: Literal["postgres", "offline-memory"]
    error: str | None = None

    @classmethod
    def offline(cls, component: Literal["queue", "checkpoint"]) -> "DurabilityComponentStatus":
        return cls(component=component, configured=False, verified=False, mode="offline-memory")

    @classmethod
    def failed(cls, component: Literal["queue", "checkpoint"]) -> "DurabilityComponentStatus":
        return cls(
            component=component,
            configured=True,
            verified=False,
            mode="postgres",
            error=f"configured {component} is unavailable",
        )


@dataclass(frozen=True)
class DurabilityStatus:
    """Typed public readiness contract; queue, checkpoints, revisions independent."""

    queue: DurabilityComponentStatus
    checkpoint: DurabilityComponentStatus
    revisions: DurabilityComponentStatus | None = None

    def _components(self) -> tuple[DurabilityComponentStatus, ...]:
        parts = [self.queue, self.checkpoint]
        if self.revisions is not None:
            parts.append(self.revisions)
        return tuple(parts)

    @property
    def ready(self) -> bool:
        return all(
            not component.configured or component.verified
            for component in self._components()
        )

    @property
    def degraded(self) -> bool:
        return all(not component.configured for component in self._components())

    def public_dict(self) -> dict[str, dict[str, object]]:
        base = {"queue": asdict(self.queue), "checkpoint": asdict(self.checkpoint)}
        if self.revisions is not None:
            base["revisions"] = asdict(self.revisions)
        return base


class DurabilityRuntime:
    """Owns durable connection lifetimes for one application instance."""

    def __init__(
        self,
        *,
        status: DurabilityStatus,
        job_store: MemoryJobStore | None,
        checkpointer: Any | None,
        checkpointer_context: Any | None = None,
    ) -> None:
        self.status = status
        self.job_store = job_store
        self.checkpointer = checkpointer
        self._checkpointer_context = checkpointer_context

    def close(self) -> None:
        if self._checkpointer_context is not None:
            context, self._checkpointer_context = self._checkpointer_context, None
            context.__exit__(None, None, None)


@dataclass
class Job:
    id: str
    case_id: str
    revision_id: str
    state: str = "queued"
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    attempt_count: int = 0
    max_attempts: int = 5
    fencing_token: int = 0
    payload: dict = field(default_factory=dict)
    last_error: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryJobStore:
    """Thread-safe in-memory store implementing queue/lease/fencing semantics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}

    def enqueue(self, case_id: str, revision_id: str, payload: dict | None = None,
                max_attempts: int = 5) -> Job:
        with self._lock:
            for job in self._jobs.values():
                if (job.case_id == case_id and job.revision_id == revision_id
                        and job.state in ACTIVE_STATES):
                    raise JobConflictError(
                        f"active job {job.id} already exists for revision {revision_id}")
            job = Job(id=f"job-{uuid.uuid4().hex[:12]}", case_id=case_id,
                      revision_id=revision_id, payload=dict(payload or {}),
                      max_attempts=max_attempts)
            self._jobs[job.id] = job
            return job

    def lease(self, worker_id: str, lease_seconds: int = 60) -> Job | None:
        now = _utcnow()
        with self._lock:
            candidate = None
            for job in self._jobs.values():
                expired = (job.lease_expires_at is None or job.lease_expires_at <= now)
                if job.state == "queued" and expired:
                    candidate = job
                    break
                if job.state == "running" and expired:
                    candidate = job
                    break
            if candidate is None:
                return None
            candidate.state = "running"
            candidate.lease_owner = worker_id
            candidate.lease_expires_at = now + timedelta(seconds=lease_seconds)
            candidate.attempt_count += 1
            candidate.fencing_token += 1
            return candidate

    def heartbeat(self, job_id: str, fencing_token: int,
                  lease_seconds: int = 60) -> Job:
        with self._lock:
            job = self._require(job_id)
            self._check_token(job, fencing_token)
            if job.state not in ("running", "waiting_review"):
                raise StaleLeaseError(f"job {job_id} is {job.state}; lease lost")
            job.lease_expires_at = _utcnow() + timedelta(seconds=lease_seconds)
            return job

    def mark_waiting_review(self, job_id: str, fencing_token: int) -> Job:
        return self._transition(job_id, fencing_token, "waiting_review")

    def complete(self, job_id: str, fencing_token: int, result: dict | None = None) -> Job:
        job = self._transition(job_id, fencing_token, "completed")
        if result is not None:
            job.payload = dict(result)
        return job

    def fail(self, job_id: str, fencing_token: int, error: str) -> Job:
        with self._lock:
            job = self._require(job_id)
            self._check_token(job, fencing_token)
            job.last_error = error
            if job.attempt_count >= job.max_attempts:
                job.state = "failed"
                job.lease_owner = None
                job.lease_expires_at = None
            else:
                job.state = "queued"  # retryable; lease released
                job.lease_owner = None
                job.lease_expires_at = None
            return job

    def cancel(self, job_id: str) -> Job:
        with self._lock:
            job = self._require(job_id)
            job.state = "cancelled"
            job.lease_owner = None
            job.lease_expires_at = None
            return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _require(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"unknown job {job_id}")
        return job

    @staticmethod
    def _check_token(job: Job, fencing_token: int) -> None:
        if fencing_token != job.fencing_token:
            raise StaleLeaseError(
                f"stale fencing token {fencing_token}; current is {job.fencing_token}")

    def _transition(self, job_id: str, fencing_token: int, state: str) -> Job:
        with self._lock:
            job = self._require(job_id)
            self._check_token(job, fencing_token)
            if job.state not in ("running", "waiting_review"):
                raise StaleLeaseError(f"job {job_id} is {job.state}; lease lost")
            job.state = state
            job.lease_owner = None if state in TERMINAL_STATES else job.lease_owner
            job.lease_expires_at = None if state in TERMINAL_STATES else job.lease_expires_at
            return job


class PostgresJobStore(MemoryJobStore):
    """Postgres-backed store. Falls back to memory semantics per method on error."""

    def __init__(self, dsn: str) -> None:
        super().__init__()
        self._dsn = dsn
        try:
            import psycopg  # type: ignore
        except Exception as error:
            raise RuntimeError("psycopg is required for PostgresJobStore") from error
        self._psycopg = psycopg
        self._local = threading.local()

    def _conn(self):
        if getattr(self._local, "conn", None) is None:
            self._local.conn = self._psycopg.connect(self._dsn, autocommit=True)
            with self._local.conn.cursor() as cur:
                cur.execute("select 1 from public.revision_run_jobs limit 1")
        return self._local.conn

    def _row_to_job(self, row) -> Job:
        return Job(id=row[0], case_id=row[1], revision_id=row[2], state=row[3],
                   lease_owner=row[4], lease_expires_at=row[5],
                   attempt_count=row[6], max_attempts=row[7],
                   fencing_token=row[8], payload=row[9] or {},
                   last_error=row[10])

    _COLS = ("id, case_id, revision_id, state, lease_owner, lease_expires_at,"
             " attempt_count, max_attempts, fencing_token, payload, last_error")

    def enqueue(self, case_id: str, revision_id: str, payload: dict | None = None,
                max_attempts: int = 5) -> Job:
        import json as _json
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        try:
            with self._conn().cursor() as cur:
                cur.execute(
                    "insert into public.revision_run_jobs"
                    " (id, case_id, revision_id, max_attempts, payload) values"
                    " (%s, %s, %s, %s, %s::jsonb)",
                    (job_id, case_id, revision_id, max_attempts,
                     _json.dumps(dict(payload or {}))),
                )
                cur.execute(
                    f"select {self._COLS} from public.revision_run_jobs where id = %s",
                    (job_id,),
                )
                return self._row_to_job(cur.fetchone())
        except Exception as error:
            if "duplicate" in str(error).lower() or "unique" in str(error).lower():
                raise JobConflictError(
                    f"active job already exists for revision {revision_id}") from error
            raise

    def lease(self, worker_id: str, lease_seconds: int = 60) -> Job | None:
        try:
            with self._conn().cursor() as cur:
                cur.execute(
                    f"update public.revision_run_jobs set state='running',"
                    " lease_owner=%s, lease_expires_at=now() + (%s || ' seconds')::interval,"
                    " attempt_count=attempt_count+1, fencing_token=fencing_token+1"
                    " where id = (select id from public.revision_run_jobs"
                    " where (state='queued' or (state='running' and"
                    " (lease_expires_at is null or lease_expires_at <= now())))"
                    " order by created_at limit 1 for update skip locked)"
                    f" returning {self._COLS}",
                    (worker_id, str(lease_seconds)),
                )
                row = cur.fetchone()
                return self._row_to_job(row) if row else None
        except Exception:
            raise

    def _guarded_update(self, job_id: str, fencing_token: int, set_clause: str,
                        params: tuple = ()) -> Job:
        with self._conn().cursor() as cur:
            cur.execute(
                f"select fencing_token, state from public.revision_run_jobs where id=%s",
                (job_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(f"unknown job {job_id}")
            if row[0] != fencing_token:
                raise StaleLeaseError(
                    f"stale fencing token {fencing_token}; current is {row[0]}")
            if row[1] not in ("running", "waiting_review"):
                raise StaleLeaseError(f"job {job_id} is {row[1]}; lease lost")
            cur.execute(
                f"update public.revision_run_jobs set {set_clause} where id=%s"
                f" returning {self._COLS}",
                (*params, job_id),
            )
            return self._row_to_job(cur.fetchone())

    def heartbeat(self, job_id: str, fencing_token: int,
                  lease_seconds: int = 60) -> Job:
        return self._guarded_update(
            job_id, fencing_token,
            "lease_expires_at = now() + (%s || ' seconds')::interval",
            (str(lease_seconds),))

    def mark_waiting_review(self, job_id: str, fencing_token: int) -> Job:
        return self._guarded_update(job_id, fencing_token, "state='waiting_review'")

    def complete(self, job_id: str, fencing_token: int,
                 result: dict | None = None) -> Job:
        import json as _json
        if result is None:
            return self._guarded_update(
                job_id, fencing_token,
                "state='completed', lease_owner=null, lease_expires_at=null")
        return self._guarded_update(
            job_id, fencing_token,
            "state='completed', lease_owner=null, lease_expires_at=null, payload=%s::jsonb",
            (_json.dumps(dict(result)),))

    def fail(self, job_id: str, fencing_token: int, error: str) -> Job:
        return self._guarded_update(
            job_id, fencing_token,
            "last_error=%s, state = case when attempt_count >= max_attempts"
            " then 'failed' else 'queued' end,"
            " lease_owner = case when attempt_count >= max_attempts"
            " then null else null end, lease_expires_at=null",
            (error,))

    def cancel(self, job_id: str) -> Job:
        with self._conn().cursor() as cur:
            cur.execute(
                f"update public.revision_run_jobs set state='cancelled',"
                f" lease_owner=null, lease_expires_at=null where id=%s"
                f" returning {self._COLS}",
                (job_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(f"unknown job {job_id}")
            return self._row_to_job(row)

    def get(self, job_id: str) -> Job | None:
        with self._conn().cursor() as cur:
            cur.execute(
                f"select {self._COLS} from public.revision_run_jobs where id=%s",
                (job_id,),
            )
            row = cur.fetchone()
            return self._row_to_job(row) if row else None


def job_store_from_env() -> MemoryJobStore:
    """Return a Postgres store when DATABASE_URL is set, else offline memory store."""
    dsn = (os.getenv("DATABASE_URL", "") or os.getenv("SUPABASE_DB_URL", "")).strip()
    if dsn:
        try:
            store = PostgresJobStore(dsn)
            store._conn()
            return store
        except Exception as error:
            raise DurabilityConfigurationError(
                "Configured database job queue is unavailable; refusing memory fallback") from error
    return MemoryJobStore()


def configured_database_url() -> str | None:
    """Return the configured durable DSN without exposing it in diagnostics."""
    dsn = (os.getenv("DATABASE_URL", "") or os.getenv("SUPABASE_DB_URL", "")).strip()
    return dsn or None


def _postgres_saver_class():
    """``PostgresSaver`` whose async methods run the sync ones in worker threads.

    The AG-UI agent drives the graph with ``astream_events``; the sync saver's
    ``a*`` methods raise ``NotImplementedError`` (that is what
    ``AsyncPostgresSaver`` is for, but it needs a running event loop at
    construction and this runtime is built at import). psycopg connections
    are thread-safe and ``PostgresSaver`` serializes cursor use with its own
    lock, so delegating through ``asyncio.to_thread`` is safe.
    """
    import asyncio

    from langgraph.checkpoint.postgres import PostgresSaver

    class AsyncCapablePostgresSaver(PostgresSaver):
        async def aget_tuple(self, config):
            return await asyncio.to_thread(self.get_tuple, config)

        async def alist(self, config, *, filter=None, before=None, limit=None):
            items = await asyncio.to_thread(
                lambda: list(self.list(config, filter=filter, before=before, limit=limit))
            )
            for item in items:
                yield item

        async def aput(self, config, checkpoint, metadata, new_versions):
            return await asyncio.to_thread(
                self.put, config, checkpoint, metadata, new_versions
            )

        async def aput_writes(self, config, writes, task_id, task_path=""):
            await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

        async def adelete_thread(self, thread_id):
            await asyncio.to_thread(self.delete_thread, thread_id)

    return AsyncCapablePostgresSaver


def _verify_checkpoint_schema(saver: Any) -> None:
    """Perform a read-only checkpoint query; setup is an operator action.

    ``PostgresSaver.setup`` mutates shared schema and is deliberately never
    called by the web process. ``get_tuple`` validates that the existing tables
    and migrations can be read without writing a checkpoint.
    """
    saver.get_tuple({"configurable": {"thread_id": "__readiness_probe__"}})


def build_durability_runtime(dsn: str | None = None) -> DurabilityRuntime:
    """Construct one app-owned durable runtime, retaining the saver context.

    A configured dependency failure is reported independently for queue and
    checkpoint. The process can still serve liveness/readiness endpoints, but
    business traffic must be gated by the caller until both verify.
    """
    dsn = dsn if dsn is not None else configured_database_url()
    if not dsn:
        from langgraph.checkpoint.memory import MemorySaver

        return DurabilityRuntime(
            status=DurabilityStatus(
                queue=DurabilityComponentStatus.offline("queue"),
                checkpoint=DurabilityComponentStatus.offline("checkpoint"),
            ),
            job_store=MemoryJobStore(),
            checkpointer=MemorySaver(),
        )

    job_store: MemoryJobStore | None = None
    try:
        job_store = PostgresJobStore(dsn)
        job_store._conn()
        queue_status = DurabilityComponentStatus(
            component="queue", configured=True, verified=True, mode="postgres"
        )
    except Exception:
        queue_status = DurabilityComponentStatus.failed("queue")

    saver: Any | None = None
    saver_context: Any | None = None
    try:
        saver_context = _postgres_saver_class().from_conn_string(dsn)
        saver = saver_context.__enter__()
        _verify_checkpoint_schema(saver)
        checkpoint_status = DurabilityComponentStatus(
            component="checkpoint", configured=True, verified=True, mode="postgres"
        )
    except Exception:
        if saver_context is not None:
            saver_context.__exit__(None, None, None)
        saver_context = None
        saver = None
        checkpoint_status = DurabilityComponentStatus.failed("checkpoint")

    return DurabilityRuntime(
        status=DurabilityStatus(queue=queue_status, checkpoint=checkpoint_status),
        job_store=job_store,
        checkpointer=saver,
        checkpointer_context=saver_context,
    )


def durable_checkpointer():
    """Compatibility helper for intentional offline execution only.

    Production code must use :func:`build_durability_runtime` so that the
    ``from_conn_string`` context manager remains alive for the graph lifetime.
    """
    if configured_database_url():
        raise DurabilityConfigurationError(
            "Configured checkpointer requires an application-owned durability runtime"
        )
    return build_durability_runtime().checkpointer


# Small helper so CPU-heavy parsing runs off the request event loop.
def run_in_worker_thread(func, *args, **kwargs):
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(func, *args, **kwargs).result()


def utcnow_iso() -> str:
    return _utcnow().isoformat()


def lease_ttl_expired(expires_at: datetime | None,
                      now: datetime | None = None) -> bool:
    return expires_at is None or expires_at <= (now or _utcnow())


def short_sleep_for_tests() -> None:
    time.sleep(0.01)
