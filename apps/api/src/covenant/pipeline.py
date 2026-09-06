"""Covenant run pipeline: from an uploaded document to persisted run state.

A worker leases a revision-run job and drives it through ``CasePipeline``::

    pipeline = CasePipeline(dsn, storage)
    pipeline.begin(job)                      # run_state -> 'running'
    result = pipeline.run(job, on_progress)  # persist + finalize

``dsn`` of None selects the in-memory implementation (dicts shadowing the
same shapes as the Postgres tables); otherwise Postgres via psycopg with
short transactions and parameterized SQL only.

Money travels as exact strings on the wire (``result["calculation"]``) and
as numeric in Postgres (Decimal/str bound with ``::numeric`` casts).
Domain events carry identifiers, hashes, and counts only -- never raw
document text.

Memory mode: all state lives on the instance (``_run_states``,
``_artifacts``, ``_rules``, ``_facts``, ``_events``). Reconstruction from a
new instance is N/A for memory -- a fresh ``CasePipeline(None, ...)`` starts
empty and cannot see another instance's dicts. Durability across
reconstruction is a Postgres-only property, covered by the Postgres tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from decimal import Decimal, ROUND_HALF_UP

from pathlib import Path

from src.covenant import ingestion
from src.covenant.documents import DocumentService, UnknownDocumentError
from src.covenant.policy import period_end

_TWO_PLACES = Decimal("0.01")
_EVIDENCE_PERIOD_START = "2023-01-01"
_EVIDENCE_PERIOD_END = "2023-12-31"
_UNIT_SCALE_USD_MILLIONS = 1_000_000

_SUPPORTED_ARTIFACT_TYPES = (
    "calculation",
    "coverage",
    "evidence_manifest",
    "audit_trace",
    "draft_package",
)


class PipelineError(Exception):
    """Base error for covenant pipeline failures."""


class TransientRunError(PipelineError):
    """Retryable failure (e.g. a storage blip); the worker should retry."""


class PermanentRunError(PipelineError):
    """Non-retryable failure (e.g. unknown document); the worker must not retry."""


def _exact(value: object) -> str:
    return str(Decimal(str(value)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP))


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _content_hash(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CasePipeline:
    """Drive one revision-run job from document bytes to persisted results."""

    def __init__(self, dsn: str | None, storage, revision_repository=None) -> None:
        """``revision_repository`` (memory mode only): share the API's
        MemoryRevisionRepository so RUN_* events, run_state and artifacts show
        up in its snapshot. Postgres mode always reads/writes the tables."""
        self._dsn = dsn
        self._storage = storage
        self.documents = DocumentService(dsn, storage)
        # Memory mode mirrors of the Postgres tables, keyed by (case, revision).
        self._run_states: dict[tuple[str, str], str] = {}
        self._rules: dict[tuple[str, str, str], dict] = {}
        self._facts: dict[tuple[str, str, str], dict] = {}
        self._artifacts: dict[tuple[str, str], list[dict]] = {}
        self._events: dict[tuple[str, str], list[dict]] = {}
        self._events_repo = revision_repository  # memory revision repo for RUN_* events
        # Fixture-case provider for recalculation jobs on revisions without
        # uploaded documents: ``case_provider(case_id) -> CovenantCase``.
        # Wired by the API worker and the standalone worker entry point;
        # absent means fixture recalculation is unavailable (fail-closed).
        self.case_provider = None
        if dsn is None and hasattr(revision_repository, "bind_pipeline"):
            revision_repository.bind_pipeline(self)

    # -- public API -------------------------------------------------

    def begin(self, job) -> None:
        """Mark the revision running and append a RUN_STARTED event."""
        org = self._resolve_org(job)
        case_id = job.case_id
        revision_id = job.revision_id
        if self._dsn is None:
            self._set_run_state(org, case_id, revision_id, "running")
        else:
            import psycopg

            with psycopg.connect(self._dsn, autocommit=False) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "update public.case_revisions set run_state = 'running'"
                        " where case_id = %s and revision_id = %s"
                        " and organization_id = %s",
                        (case_id, revision_id, org),
                    )
                    if cur.rowcount == 0:
                        raise PermanentRunError(
                            f"unknown revision {revision_id} for case {case_id}"
                        )
                conn.commit()
        self._append_event(
            case_id, org, revision_id, job.id, "RUN_STARTED", {"job_id": job.id}
        )

    def run(self, job, on_progress: Callable[[], None]) -> dict:
        """Load, extract, persist, and finalize one job.

        Returns ``{"status", "revision_id", "artifacts", "calculation",
        "error"}``. The unsupported path is done-work, not failure: it
        returns ``status="waiting_review"`` with an evidence manifest and no
        invented figures. Jobs carrying ``{"recalculation": True}`` re-run
        the deterministic calculator for the same revision after a review
        decision instead of extracting a new document.
        """
        payload = dict(job.payload or {})
        if payload.get("recalculation"):
            return self._run_recalculation(job, on_progress)
        document_id = payload.get("document_id")
        case_id = job.case_id
        revision_id = job.revision_id

        # (1) load latest doc version + bytes.
        org = self._resolve_org(job)
        try:
            version, data = self.documents.read_bytes(document_id, org)
        except UnknownDocumentError as error:
            raise PermanentRunError(f"unknown document {document_id}") from error
        except FileNotFoundError as error:
            raise TransientRunError(f"storage unavailable for {document_id}") from error
        self._append_event(
            case_id, org, revision_id, job.id, "DOCUMENT_READ",
            {"job_id": job.id, "document_id": document_id,
             "media_type": version.media_type,
             "filename": version.title},
        )
        on_progress()

        # (2) extraction: the uploaded bytes first, then the case's latest
        # document of the matching role, then the bundled Aon fixture. Every
        # result records where it came from so nothing is silently invented.
        # The rule must come from real case evidence (never a fixture): an
        # upload that yields no covenant stays unsupported.
        rule, rule_source = self._extract(
            ingestion.extract_aon_rule, version, data, org, case_id,
            "credit_agreement", None, "",
        )
        facts, fact_source = None, {"kind": "skipped",
                                    "reason": "no covenant rule extracted"}
        if rule is not None:
            self._append_event(
                case_id, org, revision_id, job.id, "AGREEMENT_RESOLVED",
                {"job_id": job.id, "document_id": document_id},
            )
            facts, fact_source = self._extract(
                ingestion.extract_aon_financials, version, data, org, case_id,
                "financial_statement",
                None,
                "",
            )
        on_progress()
        sources = {"rule": rule_source, "facts": fact_source}

        sha = hashlib.sha256(bytes(data)).hexdigest()
        if rule is None or facts is None:
            return self._finish_unsupported(
                job, on_progress, version, sha, "unsupported", sources
            )
        return self._finish_supported(job, on_progress, version, rule, facts, sources)

    def set_run_state(self, job, state: str) -> None:
        """Worker hook: record a terminal state ('failed'/'cancelled') for the job's revision."""
        self._set_run_state(self._resolve_org(job), job.case_id, job.revision_id, state)

    # -- extraction sources ------------------------------------------

    def _extract(self, extractor, version, data, org, case_id, role,
                 bundled: Path | None, bundled_label: str) -> tuple[object | None, dict]:
        """Return ``(extracted, source)``; ``extracted`` is None when nothing parsed.

        Order: the uploaded bytes, the case's latest *role* document, then
        *bundled* (a labelled repo fixture) when one is given.
        """
        candidates = [("upload", version, bytes(data))]
        other = self._latest_case_document(org, case_id, role, exclude=version.document_id)
        if other is not None:
            candidates.append(("case_document", other[0], other[1]))
        for kind, ver, blob in candidates:
            result = self._extract_bytes(extractor, blob)
            if result is not None:
                return result, {"kind": kind, "document_id": ver.document_id,
                                "sha256": ver.sha256}
        attempted = [c[0] for c in candidates]
        if bundled is None:
            return None, {"kind": "none", "attempted": attempted}
        try:
            result = extractor(bundled)
        except Exception:
            return None, {"kind": "none", "attempted": attempted + ["bundled_fixture"]}
        return result, {"kind": "bundled_fixture", "label": bundled_label,
                        "path": f"data/raw/{bundled.relative_to(ingestion.data_root())}",
                        "sha256": _file_sha256(bundled)}

    @staticmethod
    def _extract_bytes(extractor, blob: bytes):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
            handle.write(blob)
            tmp_path = handle.name
        try:
            return extractor(Path(tmp_path))
        except Exception:
            return None
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _latest_case_document(self, org: str, case_id: str, role: str, exclude: str):
        """Latest (version, bytes) of the case's newest *role* document, or None."""
        if self._dsn is None:
            docs = [d for d in self.documents._documents.values()  # noqa: SLF001
                    if d.case_id == case_id and d.organization_id == org
                    and d.document_role == role and d.id != exclude]
            doc_id = docs[-1].id if docs else None
        else:
            import psycopg

            with psycopg.connect(self._dsn, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "select id from public.documents"
                        " where organization_id = %s and case_id = %s"
                        " and document_role = %s and id <> %s"
                        " order by created_at desc limit 1",
                        (org, case_id, role, exclude),
                    )
                    row = cur.fetchone()
                    doc_id = str(row[0]) if row else None
        if doc_id is None:
            return None
        try:
            return self.documents.read_bytes(doc_id, org)
        except (UnknownDocumentError, FileNotFoundError):
            return None

    # -- reads (both modes) ------------------------------------------

    def run_state(self, case_id: str, revision_id: str) -> str | None:
        """Current run_state for (case, revision), or None if unknown."""
        if self._dsn is None:
            return self._run_states.get((case_id, revision_id))
        import psycopg

        with psycopg.connect(self._dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select run_state from public.case_revisions"
                    " where case_id = %s and revision_id = %s",
                    (case_id, revision_id),
                )
                row = cur.fetchone()
                return row[0] if row else None

    def artifacts_for(self, case_id: str, revision_id: str) -> list[dict]:
        """Current artifacts for (case, revision), oldest first."""
        if self._dsn is None:
            rows = [
                dict(a)
                for a in self._artifacts.get((case_id, revision_id), [])
                if a["state"] == "current"
            ]
            return sorted(rows, key=lambda a: a["artifact_type"])
        import psycopg

        with psycopg.connect(self._dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select artifact_type, content_hash, payload"
                    " from public.artifacts"
                    " where case_id = %s and revision_id = %s"
                    " and state = 'current' order by artifact_type",
                    (case_id, revision_id),
                )
                return [
                    {
                        "artifact_type": r[0],
                        "content_hash": r[1],
                        "payload": r[2] if isinstance(r[2], dict) else json.loads(r[2]),
                    }
                    for r in cur.fetchall()
                ]

    # -- internals ---------------------------------------------------

    def _resolve_org(self, job) -> str:
        payload = dict(job.payload or {})
        if payload.get("recalculation") and payload.get("organization_id"):
            # Recalculation jobs carry no document; the org travels in the
            # payload set by the review-resolution route.
            return str(payload["organization_id"])
        document_id = payload.get("document_id")
        if self._dsn is None:
            try:
                location = self.documents.find_location(document_id)
            except UnknownDocumentError as error:
                raise PermanentRunError(
                    f"unknown document {document_id}"
                ) from error
            if location["case_id"] != job.case_id:
                raise PermanentRunError(
                    f"document {document_id} does not belong to case {job.case_id}"
                )
            return str(location["organization_id"])
        from .revision_repository import PostgresRevisionRepository
        from src.covenant.revisions import UnknownRevisionError

        try:
            return PostgresRevisionRepository(self._dsn).get_case_org(job.case_id)
        except (UnknownDocumentError, UnknownRevisionError) as error:
            raise PermanentRunError(f"unknown case {job.case_id}") from error

    def _append_event(
        self,
        case_id: str,
        org: str,
        revision_id: str | None,
        run_id: str | None,
        event_type: str,
        summary: dict,
    ) -> dict:
        if self._dsn is None:
            if self._events_repo is None:
                from .revision_repository import MemoryRevisionRepository

                self._events_repo = MemoryRevisionRepository()
            try:
                self._events_repo.ensure_case(
                    case_id, org, "pipeline", "2026-01-01", "pipeline",
                    "0.00", [], [],
                )
            except Exception:
                pass
            try:
                event = self._events_repo.append_event(
                    case_id, org, revision_id, run_id, event_type, dict(summary)
                )
            except Exception:
                event = {"name": event_type, "revision_id": revision_id,
                         "run_id": run_id, "summary": dict(summary)}
            self._events.setdefault((case_id, revision_id or ""), []).append(event)
            return event
        try:
            from .revision_repository import PostgresRevisionRepository

            repo = PostgresRevisionRepository(self._dsn)
        except Exception:
            from .revision_repository import PostgresRevisionRepository

            repo = PostgresRevisionRepository(self._dsn)
        return repo.append_event(
            case_id, org, revision_id, run_id, event_type, dict(summary)
        )

    def _store_artifact(
        self,
        org: str,
        case_id: str,
        revision_id: str,
        artifact_type: str,
        payload: dict,
    ) -> dict:
        content_hash = _content_hash(payload)
        if self._dsn is None:
            from datetime import datetime, timezone

            rows = self._artifacts.setdefault((case_id, revision_id), [])
            for row in rows:
                if row["artifact_type"] == artifact_type and row["state"] == "current":
                    if row["content_hash"] == content_hash:
                        return dict(row)
                    row["state"] = "stale"
            record = {
                "artifact_type": artifact_type,
                "content_hash": content_hash,
                "payload": json.loads(_canonical(payload)),
                "state": "current",
                # Record-level only: never part of the hashed payload.
                # Lets approval prove the calculation postdates the review.
                "stored_at": datetime.now(timezone.utc).isoformat(),
            }
            rows.append(record)
            return dict(record)
        import psycopg

        with psycopg.connect(self._dsn, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select id, content_hash from public.artifacts"
                    " where organization_id = %s and case_id = %s and revision_id = %s"
                    " and artifact_type = %s and state = 'current'",
                    (org, case_id, revision_id, artifact_type),
                )
                existing = cur.fetchall()
                for _, existing_hash in existing:
                    if str(existing_hash) == content_hash:
                        conn.commit()
                        return {
                            "artifact_type": artifact_type,
                            "content_hash": content_hash,
                            "payload": payload,
                            "state": "current",
                        }
                cur.execute(
                    "update public.artifacts set state = 'stale'"
                    " where organization_id = %s and case_id = %s and revision_id = %s"
                    " and artifact_type = %s and state = 'current'",
                    (org, case_id, revision_id, artifact_type),
                )
                cur.execute(
                    "insert into public.artifacts"
                    " (organization_id, case_id, revision_id, artifact_type,"
                    " content_hash, payload, state)"
                    " values (%s, %s, %s, %s, %s, %s::jsonb, 'current')",
                    (org, case_id, revision_id, artifact_type,
                     content_hash, _canonical(payload)),
                )
            conn.commit()
        return {
            "artifact_type": artifact_type,
            "content_hash": content_hash,
            "payload": payload,
            "state": "current",
        }

    def _set_run_state(
        self, org: str, case_id: str, revision_id: str, state: str
    ) -> None:
        if self._dsn is None:
            self._run_states[(case_id, revision_id)] = state
            if hasattr(self._events_repo, "set_run_state"):
                self._events_repo.set_run_state(case_id, revision_id, state)
            return
        import psycopg

        with psycopg.connect(self._dsn, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update public.case_revisions set run_state = %s"
                    " where case_id = %s and revision_id = %s"
                    " and organization_id = %s",
                    (state, case_id, revision_id, org),
                )
            conn.commit()

    def _set_package_ready(
        self, org: str, case_id: str, revision_id: str
    ) -> None:
        """Promote a recomputed draft to officer review (draft -> ready only).

        Never overwrites an approved draft; a replayed recalculation is a
        no-op success.
        """
        if self._dsn is None:
            repo = self._events_repo
            mark = getattr(repo, "mark_package_ready", None)
            if mark is None:
                raise PermanentRunError("no revision repository bound")
            try:
                mark(case_id, revision_id)
            except (KeyError, LookupError) as error:
                raise PermanentRunError(
                    f"unknown revision {revision_id} for case {case_id}"
                ) from error
            return
        import psycopg

        with psycopg.connect(self._dsn, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update public.case_revisions"
                    " set package_state = 'ready_for_officer_review'"
                    " where case_id = %s and revision_id = %s"
                    " and organization_id = %s and package_state = 'draft'",
                    (case_id, revision_id, org),
                )
            conn.commit()

    # -- recalculation path ------------------------------------------

    #: Review decision kind -> calculator decision for the recomputation.
    _RECALC_DECISIONS = {
        "accept_evidence": "approve_addback",
        "reject_evidence": "reject_addback",
        "correct_mapping": "pending",
    }

    def _run_recalculation(self, job, on_progress: Callable[[], None]) -> dict:
        """Recompute one revision deterministically after a review decision.

        Uses the authoritative fixture case at the head revision's threshold,
        overlaid with persisted fact amounts when the revision already has
        pipeline rows, and the typed Decimal calculator. Persists fresh
        calculation/coverage/trace/package artifacts (stale rotation),
        completes the run, and promotes the package to ready only when zero
        blocking issues remain.
        """
        from src.covenant.calculator import CovenantCalculator
        from src.covenant.domain import ReviewerDecision, money_str

        payload = dict(job.payload or {})
        org = self._resolve_org(job)
        case_id = job.case_id
        revision_id = job.revision_id
        decision_kind = str(payload.get("decision_kind") or "")
        calc_decision = ReviewerDecision(
            self._RECALC_DECISIONS.get(decision_kind, "pending")
        )
        head_threshold, _ = self._recalculation_head(case_id, org, revision_id)
        on_progress()
        computed = self._recompute_revision(
            case_id, org, revision_id, head_threshold, calc_decision)
        on_progress()
        if computed is None:
            # Missing facts or zero denominator: still paused, never ready.
            self._set_run_state(org, case_id, revision_id, "waiting_review")
            self._append_event(
                case_id, org, revision_id, job.id, "REVIEW_REQUIRED",
                {"job_id": job.id, "revision_id": revision_id,
                 "reason": "recalculation produced no ratio"},
            )
            self._append_event(
                case_id, org, revision_id, job.id, "RUN_COMPLETED",
                {"job_id": job.id, "revision_id": revision_id,
                 "status": "waiting_review"},
            )
            on_progress()
            return {"status": "waiting_review", "revision_id": revision_id,
                    "artifacts": [], "calculation": None, "error": None}
        ratio_s = computed["ratio"]
        threshold_s = computed["threshold"]
        calc_payload = {
            "ratio": ratio_s,
            "threshold": threshold_s,
            "comparator": computed["comparator"],
            "formula": computed["formula"],
            "inputs": computed["inputs"],
            "decision_kind": decision_kind,
            "job_id": job.id,
            "recalculation": True,
        }
        coverage_payload = {
            "status": "complete_for_declared_scope",
            "assessed": [computed.get("rule_id", "")],
            "excluded": [],
        }
        stored_calc = self._store_artifact(
            org, case_id, revision_id, "calculation", calc_payload)
        stored_coverage = self._store_artifact(
            org, case_id, revision_id, "coverage", coverage_payload)
        trace_payload = {
            "job_id": job.id,
            "revision_id": revision_id,
            "decision_kind": decision_kind,
            "stages": ["recalculate", "finalize"],
            "calculation_hash": stored_calc["content_hash"],
        }
        stored_trace = self._store_artifact(
            org, case_id, revision_id, "audit_trace", trace_payload)
        package_payload = {
            "revision_id": revision_id,
            "status": "draft",
            "calculation_hash": stored_calc["content_hash"],
            "coverage_hash": stored_coverage["content_hash"],
            "manifest_hash": self._current_artifact_hash(
                case_id, revision_id, org, "evidence_manifest")
            or stored_calc["content_hash"],
            "trace_hash": stored_trace["content_hash"],
        }
        stored_package = self._store_artifact(
            org, case_id, revision_id, "draft_package", package_payload)
        on_progress()
        self._set_run_state(org, case_id, revision_id, "completed")
        self._append_event(
            case_id, org, revision_id, job.id, "CALCULATION_COMPLETED",
            {"job_id": job.id, "revision_id": revision_id,
             "ratio": ratio_s, "threshold": threshold_s,
             "decision_kind": decision_kind},
        )
        self._append_event(
            case_id, org, revision_id, job.id, "RECALCULATION_COMPLETED",
            {"job_id": job.id, "revision_id": revision_id,
             "decision_kind": decision_kind},
        )
        self._append_event(
            case_id, org, revision_id, job.id, "RUN_COMPLETED",
            {"job_id": job.id, "revision_id": revision_id,
             "status": "completed"},
        )
        on_progress()
        # Readiness is rechecked after the recomputation, never assumed:
        # only a completed current run with zero blocking issues may wait
        # for the officer.
        _, open_issues = self._recalculation_head(case_id, org, revision_id)
        if open_issues == 0:
            self._set_package_ready(org, case_id, revision_id)
            self._append_event(
                case_id, org, revision_id, job.id, "PACKAGE_REVISED",
                {"job_id": job.id, "revision_id": revision_id},
            )
        stored = [stored_calc, stored_coverage, stored_trace, stored_package]
        return {
            "status": "completed",
            "revision_id": revision_id,
            "artifacts": [
                {"artifact_type": a["artifact_type"],
                 "content_hash": a["content_hash"]} for a in stored
            ],
            "calculation": {
                "ratio": ratio_s,
                "threshold": threshold_s,
                "comparator": computed["comparator"],
            },
            "error": None,
        }

    def _recalculation_head(self, case_id: str, org: str,
                            revision_id: str) -> tuple[str, int]:
        """Return (head threshold, open issue count), rejecting stale jobs."""
        if self._dsn is None:
            repo = self._events_repo
            snapshot = getattr(repo, "snapshot", None)
            if snapshot is None:
                raise PermanentRunError("no revision repository bound")
            try:
                snap = snapshot(case_id)
            except (KeyError, LookupError) as error:
                raise PermanentRunError(
                    f"unknown case {case_id}") from error
            if snap["revision"]["revision_id"] != revision_id:
                raise PermanentRunError(
                    f"recalculation targets superseded revision {revision_id}")
            return (str(snap["revision"]["threshold"]),
                    int(snap["open_review_issues"]))
        import psycopg

        with psycopg.connect(self._dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select revision_id, threshold from public.case_revisions"
                    " where case_id = %s and organization_id = %s"
                    " order by created_at desc limit 1",
                    (case_id, org),
                )
                row = cur.fetchone()
                if row is None or str(row[0]) != revision_id:
                    raise PermanentRunError(
                        f"recalculation targets superseded revision {revision_id}")
                cur.execute(
                    "select count(*) from public.review_issues"
                    " where case_id = %s and organization_id = %s"
                    " and revision_id = %s and status = 'open'",
                    (case_id, org, revision_id),
                )
                return (str(row[1]), int(cur.fetchone()[0]))

    #: EBITDA component keys shared with the supported upload path: a
    #: recalculation on a revision with persisted evidence must reproduce
    #: the worker's arithmetic exactly, never a different formula.
    _RECALC_EBITDA_KEYS = ("net_income", "income_tax", "interest_expense",
                           "depreciation", "amortization")

    def _recompute_revision(self, case_id: str, org: str, revision_id: str,
                            head_threshold: str, calc_decision) -> dict | None:
        """Deterministic Decimal recomputation; None when no ratio issues.

        Revisions with persisted pipeline evidence reuse the supported
        path's arithmetic over those amounts at the head threshold.
        Revisions without uploads compute from the authoritative fixture
        case at the head threshold. Both stay in typed Python Decimal.
        """
        comparator, persisted, rule_id = self._persisted_rule_and_facts(
            case_id, revision_id, org)
        if comparator is not None and persisted:
            amounts = {}
            for key in (*self._RECALC_EBITDA_KEYS, "funded_debt"):
                raw = persisted.get(key)
                if raw is None:
                    return None
                amounts[key] = Decimal(str(raw))
            ebitda = sum((amounts[k] for k in self._RECALC_EBITDA_KEYS),
                         Decimal("0"))
            funded_debt = amounts["funded_debt"]
            if ebitda == 0:
                return None
            ratio = (funded_debt / ebitda).quantize(
                _TWO_PLACES, rounding=ROUND_HALF_UP)
            return {
                "ratio": _exact(ratio),
                "threshold": _exact(Decimal(str(head_threshold))),
                "comparator": comparator,
                "formula": "Consolidated Funded Debt / Consolidated Adjusted EBITDA",
                "rule_id": rule_id or "",
                "inputs": {k: _exact(v) for k, v in persisted.items()},
            }
        case = self._recalculation_case(case_id, head_threshold)
        from src.covenant.calculator import CovenantCalculator
        from src.covenant.domain import money_str

        calculation, _calc_issues = CovenantCalculator().calculate(
            case, calc_decision)
        if calculation.ratio is None:
            return None
        return {
            "ratio": money_str(calculation.ratio),
            "threshold": money_str(calculation.threshold),
            "comparator": calculation.comparator,
            "formula": case.rule.formula_label,
            "rule_id": case.rule.id,
            "inputs": {line.fact_key: money_str(line.amount)
                       for line in calculation.lines if line.included},
        }

    def _recalculation_case(self, case_id: str, head_threshold: str):
        """Authoritative fixture case at the head revision's threshold."""
        provider = self.case_provider
        if provider is None:
            raise PermanentRunError(
                "fixture recalculation is unavailable: no case provider")
        try:
            base = provider(case_id)
        except Exception as error:
            raise PermanentRunError(
                f"unknown case {case_id}") from error
        return base.model_copy(update={"rule": base.rule.model_copy(
            update={"threshold": float(head_threshold)})})

    def _persisted_rule_and_facts(self, case_id: str, revision_id: str,
                                  org: str) -> tuple[str | None, dict, str | None]:
        """Persisted (comparator, {fact_key: amount}, rule id) for a revision."""
        if self._dsn is None:
            comparator, rule_id = None, None
            for (c, r, _), row in self._rules.items():
                if c == case_id and r == revision_id:
                    comparator = row.get("comparator")
                    rule_id = row.get("external_rule_id")
                    break
            amounts = {key: row["amount"]
                       for (c, r, key), row in self._facts.items()
                       if c == case_id and r == revision_id}
            return comparator, amounts, rule_id
        import psycopg

        with psycopg.connect(self._dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select comparator, external_rule_id from public.covenant_rules"
                    " where case_id = %s and revision_id = %s limit 1",
                    (case_id, revision_id),
                )
                rule = cur.fetchone()
                cur.execute(
                    "select fact_key, amount from public.financial_facts"
                    " where case_id = %s and revision_id = %s",
                    (case_id, revision_id),
                )
                return ((str(rule[0]) if rule else None),
                        {str(k): str(v) for k, v in cur.fetchall()},
                        (str(rule[1]) if rule else None))

    def _current_artifact_hash(self, case_id: str, revision_id: str, org: str,
                               artifact_type: str) -> str | None:
        if self._dsn is None:
            rows = [a for a in self._artifacts.get((case_id, revision_id), [])
                    if a["artifact_type"] == artifact_type
                    and a["state"] == "current"]
            return rows[-1]["content_hash"] if rows else None
        import psycopg

        with psycopg.connect(self._dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select content_hash from public.artifacts"
                    " where organization_id = %s and case_id = %s"
                    " and revision_id = %s and artifact_type = %s"
                    " and state = 'current' order by created_at desc limit 1",
                    (org, case_id, revision_id, artifact_type),
                )
                row = cur.fetchone()
                return str(row[0]) if row else None

    # -- supported path -----------------------------------------------

    def _finish_supported(
        self, job, on_progress: Callable[[], None], version, rule, facts,
        sources: dict | None = None,
    ) -> dict:
        org = self._resolve_org(job)
        case_id = job.case_id
        revision_id = job.revision_id
        sources = sources or {}
        fact_source = sources.get("facts") or {"kind": "upload"}
        measurement_period = f"Measurement Period ended {ingestion.AON_TEST_DATE}"
        fact_map = {fact.key: fact for fact in facts}

        def part(key: str) -> Decimal:
            fact = fact_map.get(key)
            if fact is None:
                raise PermanentRunError(f"missing extracted fact {key}")
            return Decimal(str(fact.amount))

        ebitda = (
            part("net_income") + part("income_tax") + part("interest_expense")
            + part("depreciation") + part("amortization")
        )
        funded_debt = part("funded_debt")
        if ebitda == 0:
            return self._finish_unsupported(
                job, on_progress, version,
                hashlib.sha256(funded_debt.to_eng_string().encode()).hexdigest(),
                "unsupported", sources,
            )
        ratio = (funded_debt / ebitda).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        threshold = Decimal(str(rule.tiers[0].threshold)).quantize(
            _TWO_PLACES, rounding=ROUND_HALF_UP
        )
        ratio_s = str(ratio)
        threshold_s = str(threshold)

        external_rule_id = "aon-max-consolidated-leverage"
        structured_rule = {
            "tiers": [
                {"step": tier.step, "threshold": _exact(tier.threshold)}
                for tier in rule.tiers
            ],
            "formula": rule.formula_label,
        }
        source_spans = [
            {"kind": "covenant_section", "section": rule.section,
             "page": rule.section_page},
            {"kind": "definition", "section": "1.01",
             "page": rule.definition_page},
            {"kind": "document_hash", "sha256": rule.document_hash},
        ]
        if self._dsn is None:
            self._rules[(case_id, revision_id, external_rule_id)] = {
                "external_rule_id": external_rule_id,
                "covenant_type": "max_leverage",
                "support_state": "supported",
                "comparator": rule.comparator,
                "threshold": threshold_s,
                "measurement_period": measurement_period,
                "structured_rule": structured_rule,
                "source_spans": source_spans,
            }
            for fact in facts:
                self._facts[(case_id, revision_id, fact.key)] = {
                    "fact_key": fact.key,
                    "amount": _exact(fact.amount),
                    "currency": "USD",
                    "unit_scale": _UNIT_SCALE_USD_MILLIONS,
                    "period_start": _EVIDENCE_PERIOD_START,
                    "period_end": _EVIDENCE_PERIOD_END,
                    "evidence_state": "accepted",
                    "source_spans": [{"locator": fact.locator, "source": fact_source}],
                }
        else:
            import psycopg

            with psycopg.connect(self._dsn, autocommit=False) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "insert into public.covenant_rules"
                        " (organization_id, case_id, revision_id,"
                        " external_rule_id, covenant_type, support_state,"
                        " comparator, threshold, measurement_period,"
                        " structured_rule, source_spans)"
                        " values (%s, %s, %s, %s, 'max_leverage', 'supported',"
                        " %s, %s::numeric, %s, %s::jsonb, %s::jsonb)"
                        " on conflict (case_id, revision_id, external_rule_id)"
                        " do update set comparator = excluded.comparator,"
                        " threshold = excluded.threshold,"
                        " structured_rule = excluded.structured_rule,"
                        " source_spans = excluded.source_spans",
                        (org, case_id, revision_id, external_rule_id,
                         rule.comparator, threshold_s, measurement_period,
                         _canonical(structured_rule), _canonical(source_spans)),
                    )
                    for fact in facts:
                        spans = _canonical([{"locator": fact.locator,
                                             "source": fact_source}])
                        cur.execute(
                            "insert into public.financial_facts"
                            " (organization_id, case_id, revision_id, fact_key,"
                            " amount, currency, unit_scale, period_start,"
                            " period_end, evidence_state, source_spans)"
                            " values (%s, %s, %s, %s, %s::numeric, 'USD', %s,"
                            " %s::date, %s::date, 'accepted', %s::jsonb)"
                            " on conflict (case_id, revision_id, fact_key)"
                            " do update set amount = excluded.amount,"
                            " evidence_state = 'accepted',"
                            " source_spans = excluded.source_spans",
                            (org, case_id, revision_id, fact.key,
                             _exact(fact.amount), _UNIT_SCALE_USD_MILLIONS,
                             _EVIDENCE_PERIOD_START, _EVIDENCE_PERIOD_END,
                             spans),
                        )
                conn.commit()
        self._append_event(
            case_id, org, revision_id, job.id, "DEFINITIONS_COMPILED",
            {"job_id": job.id, "rule_id": external_rule_id},
        )
        self._append_event(
            case_id, org, revision_id, job.id, "EVIDENCE_MAPPED",
            {"job_id": job.id, "fact_count": len(facts)},
        )
        on_progress()

        inputs = {fact.key: _exact(fact.amount) for fact in facts}
        calc_payload = {
            "ratio": ratio_s,
            "threshold": threshold_s,
            "comparator": rule.comparator,
            "ebitda": _exact(ebitda),
            "funded_debt": _exact(funded_debt),
            "formula": rule.formula_label,
            "inputs": inputs,
            "document_id": version.document_id,
            "document_sha256": version.sha256,
            "fact_source": fact_source,
            # Same deterministic check as policy.period_mismatch_issue: the
            # facts must cover the covenant test period or no verdict follows.
            "period_check": {
                "facts_period_end": _EVIDENCE_PERIOD_END,
                "measurement_period_end": period_end(measurement_period),
                "matches": _EVIDENCE_PERIOD_END == period_end(measurement_period),
                "note": "Arithmetic on extracted proxies; not a compliance verdict "
                        "unless the financial period matches the test period.",
            },
        }
        coverage_payload = {
            "status": "complete_for_declared_scope",
            "assessed": [external_rule_id],
            "excluded": [],
        }
        self._append_event(
            case_id, org, revision_id, job.id, "CALCULATION_STARTED",
            {"job_id": job.id, "rule_id": external_rule_id},
        )
        on_progress()
        stored_calc = self._store_artifact(
            org, case_id, revision_id, "calculation", calc_payload
        )
        stored_coverage = self._store_artifact(
            org, case_id, revision_id, "coverage", coverage_payload
        )
        manifest_payload = {
            "extraction_state": "supported",
            "document_id": version.document_id,
            "document_sha256": version.sha256,
            "rule_spans": source_spans,
            "fact_count": len(facts),
            "sources": sources,
        }
        stored_manifest = self._store_artifact(
            org, case_id, revision_id, "evidence_manifest", manifest_payload
        )
        trace_payload = {
            "job_id": job.id,
            "revision_id": revision_id,
            "stages": ["load", "extract", "persist", "finalize"],
            "calculation_hash": stored_calc["content_hash"],
        }
        stored_trace = self._store_artifact(
            org, case_id, revision_id, "audit_trace", trace_payload
        )
        package_payload = {
            "revision_id": revision_id,
            "status": "draft",
            "calculation_hash": stored_calc["content_hash"],
            "coverage_hash": stored_coverage["content_hash"],
            "manifest_hash": stored_manifest["content_hash"],
            "trace_hash": stored_trace["content_hash"],
        }
        stored_package = self._store_artifact(
            org, case_id, revision_id, "draft_package", package_payload
        )
        on_progress()

        self._set_run_state(org, case_id, revision_id, "completed")
        self._append_event(
            case_id, org, revision_id, job.id, "CALCULATION_COMPLETED",
            {"job_id": job.id, "revision_id": revision_id,
             "ratio": ratio_s, "threshold": threshold_s,
             "artifact_count": len(_SUPPORTED_ARTIFACT_TYPES)},
        )
        self._append_event(
            case_id, org, revision_id, job.id, "RUN_COMPLETED",
            {"job_id": job.id, "revision_id": revision_id,
             "status": "completed"},
        )
        on_progress()

        stored = [stored_calc, stored_coverage, stored_manifest,
                  stored_trace, stored_package]
        return {
            "status": "completed",
            "revision_id": revision_id,
            "artifacts": [
                {"artifact_type": a["artifact_type"],
                 "content_hash": a["content_hash"]} for a in stored
            ],
            "calculation": {
                "ratio": ratio_s,
                "threshold": threshold_s,
                "comparator": rule.comparator,
            },
            "error": None,
        }

    # -- unsupported path ----------------------------------------------

    def _finish_unsupported(
        self, job, on_progress: Callable[[], None], version, sha: str,
        extraction_state: str, sources: dict | None = None,
    ) -> dict:
        org = self._resolve_org(job)
        case_id = job.case_id
        revision_id = job.revision_id
        manifest_payload = {
            "extraction_state": extraction_state,
            "document_id": version.document_id,
            "document_sha256": version.sha256,
            "content_sha256": sha,
            "note": "extraction unsupported; awaiting officer review",
            "sources": sources or {},
        }
        stored = self._store_artifact(
            org, case_id, revision_id, "evidence_manifest", manifest_payload
        )
        on_progress()
        review_repo = self._events_repo
        if review_repo is None and self._dsn is not None:
            from .revision_repository import PostgresRevisionRepository
            review_repo = PostgresRevisionRepository(self._dsn)
        if review_repo is not None:
            head = review_repo.current(case_id)
            review_repo.open_review_issue(
                case_id, org, revision_id, head.input_bundle_hash
            )
        self._set_run_state(org, case_id, revision_id, "waiting_review")
        self._append_event(
            case_id, org, revision_id, job.id, "REVIEW_REQUIRED",
            {"job_id": job.id, "revision_id": revision_id,
             "extraction_state": extraction_state,
             "document_sha256": version.sha256},
        )
        self._append_event(
            case_id, org, revision_id, job.id, "RUN_COMPLETED",
            {"job_id": job.id, "revision_id": revision_id,
             "status": "waiting_review"},
        )
        on_progress()
        return {
            "status": "waiting_review",
            "revision_id": revision_id,
            "artifacts": [
                {"artifact_type": stored["artifact_type"],
                 "content_hash": stored["content_hash"]}
            ],
            "calculation": None,
            "error": None,
        }
