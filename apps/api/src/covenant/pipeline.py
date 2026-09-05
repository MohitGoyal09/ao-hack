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

from src.covenant import ingestion
from src.covenant.documents import DocumentService, UnknownDocumentError

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


class CasePipeline:
    """Drive one revision-run job from document bytes to persisted results."""

    def __init__(self, dsn: str | None, storage) -> None:
        self._dsn = dsn
        self._storage = storage
        self.documents = DocumentService(dsn, storage)
        # Memory mode mirrors of the Postgres tables, keyed by (case, revision).
        self._run_states: dict[tuple[str, str], str] = {}
        self._rules: dict[tuple[str, str, str], dict] = {}
        self._facts: dict[tuple[str, str, str], dict] = {}
        self._artifacts: dict[tuple[str, str], list[dict]] = {}
        self._events: dict[tuple[str, str], list[dict]] = {}
        self._events_repo = None  # lazy memory revision repo for RUN_* events

    # -- public API -------------------------------------------------

    def begin(self, job) -> None:
        """Mark the revision running and append a RUN_STARTED event."""
        org = self._resolve_org(job)
        case_id = job.case_id
        revision_id = job.revision_id
        if self._dsn is None:
            self._run_states[(case_id, revision_id)] = "running"
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
        invented figures.
        """
        payload = dict(job.payload or {})
        document_id = payload.get("document_id")
        case_id = job.case_id
        revision_id = job.revision_id

        # (1) load latest doc version + bytes.
        try:
            version, data = self.documents.read_bytes(document_id, self._resolve_org(job))
        except UnknownDocumentError as error:
            raise PermanentRunError(f"unknown document {document_id}") from error
        except FileNotFoundError as error:
            raise TransientRunError(f"storage unavailable for {document_id}") from error
        on_progress()

        # (2) extraction attempt via a temp file, cleaned up in finally.
        tmp_path = None
        rule = None
        facts = None
        extraction_state = "unsupported"
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".bin", delete=False
            ) as handle:
                handle.write(bytes(data))
                tmp_path = handle.name
            from pathlib import Path

            tmp = Path(tmp_path)
            try:
                rule = ingestion.extract_aon_rule(tmp)
                facts = ingestion.extract_aon_financials(tmp)
                extraction_state = "supported"
            except Exception:
                rule, facts = None, None
                extraction_state = "unsupported"
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        on_progress()

        sha = hashlib.sha256(bytes(data)).hexdigest()
        if rule is None or facts is None:
            return self._finish_unsupported(
                job, on_progress, version, sha, extraction_state
            )
        return self._finish_supported(job, on_progress, version, rule, facts)

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

    # -- supported path -----------------------------------------------

    def _finish_supported(
        self, job, on_progress: Callable[[], None], version, rule, facts
    ) -> dict:
        org = self._resolve_org(job)
        case_id = job.case_id
        revision_id = job.revision_id
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
                "unsupported",
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
                    "source_spans": [{"locator": fact.locator}],
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
                         rule.comparator, threshold_s,
                         ingestion.AON_FINANCIAL_PERIOD,
                         _canonical(structured_rule), _canonical(source_spans)),
                    )
                    for fact in facts:
                        spans = _canonical([{"locator": fact.locator}])
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
        on_progress()

        inputs = {fact.key: _exact(fact.amount) for fact in facts}
        calc_payload = {
            "ratio": ratio_s,
            "threshold": threshold_s,
            "comparator": rule.comparator,
            "ebitda": str(ebitda),
            "funded_debt": str(funded_debt),
            "formula": rule.formula_label,
            "inputs": inputs,
            "document_id": version.document_id,
            "document_sha256": version.sha256,
        }
        coverage_payload = {
            "status": "complete_for_declared_scope",
            "assessed": [external_rule_id],
            "excluded": [],
        }
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
        extraction_state: str,
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
        }
        stored = self._store_artifact(
            org, case_id, revision_id, "evidence_manifest", manifest_payload
        )
        on_progress()
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
