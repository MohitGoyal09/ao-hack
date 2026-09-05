"""Revision repository interface with memory and Postgres implementations.

Domain rules live in :mod:`src.covenant.revisions`; this module owns only
persistence. Money travels as exact strings at the boundary and Postgres
numeric in storage. Domain events carry identifiers and hashes only, never
raw agreement or financial text.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

from .domain import money_str
from .hashing import stable_hash
from .revisions import (
    ApprovalBinding,
    CaseRevision,
    ChangeSet,
    IdempotencyConflictError,
    ImpactSet,
    RevisionStore,
    StaleCommandError,
    UnknownRevisionError,
    issue_view,
)


class RevisionRepository(Protocol):
    """Persistence contract for change-aware revisioning."""

    def ensure_case(self, case_id: str, organization_id: str, user_id: str,
                    test_date: str, rule_id: str, threshold: Any,
                    doc_ids: list[str], fact_keys: list[str], *,
                    name: str | None = None, borrower_name: str | None = None,
                    facility_name: str | None = None) -> CaseRevision: ...
    def current(self, case_id: str) -> CaseRevision: ...
    def set_run_state(self, case_id: str, revision_id: str, state: str) -> None: ...
    def artifacts_for(self, case_id: str, revision_id: str) -> list[dict]: ...
    def get(self, case_id: str, revision_id: str) -> CaseRevision: ...
    def create_revision(self, case_id: str, organization_id: str, user_id: str,
                        expected_parent: str, change_kind: str,
                        documents: list[str], facts: list[str],
                        new_threshold: Any | None = None,
                        ) -> tuple[CaseRevision, ChangeSet, ImpactSet]: ...
    def impact(self, case_id: str, revision_id: str) -> ImpactSet: ...
    def resolve_issue(self, issue_id: str, organization_id: str, user_id: str,
                      role: str, revision_id: str, expected_bundle_hash: str,
                      decision_kind: str, rationale: str,
                      evidence_refs: list[str],
                      idempotency_key: str) -> dict: ...
    def approve(self, case_id: str, organization_id: str, user_id: str,
                role: str, revision_id: str, package_hash: str,
                decision: str, reason: str,
                approved_ratio: str | None = None,
                approved_threshold: str | None = None,
                approved_comparator: str | None = None,
                approved_inputs: dict[str, str] | None = None,
                fresh_ratio: str | None = None,
                fresh_threshold: str | None = None,
                fresh_comparator: str | None = None,
                fresh_inputs: dict[str, str] | None = None) -> ApprovalBinding: ...
    def snapshot(self, case_id: str) -> dict: ...
    def append_event(self, case_id: str, organization_id: str,
                     revision_id: str | None, run_id: str | None,
                     event_type: str,
                     redacted_summary: dict | None = None) -> dict: ...
    def list_events(self, case_id: str) -> list[dict]: ...
    def get_case_org(self, case_id: str) -> str: ...
    def get_member_role(self, organization_id: str, user_id: str) -> str | None: ...
    def get_issue_case(self, issue_id: str) -> tuple[str, str, str]: ...
    def member_orgs(self, user_id: str) -> list[tuple[str, str]]: ...


def _money(value: Any) -> str:
    return money_str(value)


def _jsonb(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    import json as _json
    return _json.loads(value)


def _artifact_map(rows: list[dict]) -> dict:
    """Snapshot view: ``{artifact_type: {**payload, "content_hash": ...}}``."""
    return {r["artifact_type"]: {**_jsonb(r.get("payload"), {}),
                                 "content_hash": r["content_hash"]} for r in rows}


class MemoryRevisionRepository:
    """Explicit offline/demo implementation backed by RevisionStore."""

    def __init__(self) -> None:
        self._store = RevisionStore()
        self._case_org: dict[str, str] = {}
        self._members: dict[tuple[str, str], str] = {}
        self._pipeline = None  # memory CasePipeline bound for artifacts/rules/facts

    def seed_member(self, organization_id: str, user_id: str, role: str) -> None:
        self._members[(organization_id, user_id)] = role

    def bind_pipeline(self, pipeline: Any) -> None:
        """Share an in-process memory CasePipeline so snapshot() sees its output."""
        self._pipeline = pipeline

    def set_run_state(self, case_id: str, revision_id: str, state: str) -> None:
        self._store.set_run_state(case_id, revision_id, state)

    def artifacts_for(self, case_id: str, revision_id: str) -> list[dict]:
        if self._pipeline is None:
            return []
        return self._pipeline.artifacts_for(case_id, revision_id)

    def _pipeline_rows(self, table: str, case_id: str, revision_id: str) -> list[dict]:
        rows = getattr(self._pipeline, table, {}) if self._pipeline is not None else {}
        return [dict(row) for (c, r, _), row in sorted(rows.items())
                if c == case_id and r == revision_id]

    def ensure_case(self, case_id: str, organization_id: str, user_id: str,
                    test_date: str, rule_id: str, threshold: Any,
                    doc_ids: list[str], fact_keys: list[str], *,
                    name: str | None = None, borrower_name: str | None = None,
                    facility_name: str | None = None) -> CaseRevision:
        existing_org = self._case_org.get(case_id)
        if existing_org is not None and existing_org != organization_id:
            raise UnknownRevisionError(case_id)
        self._case_org.setdefault(case_id, organization_id)
        if (organization_id, user_id) not in self._members:
            self._members[(organization_id, user_id)] = "treasury_reviewer"
        # RevisionStore.ensure_case is idempotent per case and takes a float
        # threshold; convert the exact string through Decimal first.
        rev = self._store.ensure_case(
            case_id=case_id, test_date=test_date, rule_id=rule_id,
            threshold=float(Decimal(str(threshold))),
            doc_ids=doc_ids, fact_keys=fact_keys,
        )
        return rev

    def current(self, case_id: str) -> CaseRevision:
        return self._store.current(case_id)

    def get(self, case_id: str, revision_id: str) -> CaseRevision:
        return self._store.get(case_id, revision_id)

    def create_revision(self, case_id: str, organization_id: str, user_id: str,
                        expected_parent: str, change_kind: str,
                        documents: list[str], facts: list[str],
                        new_threshold: Any | None = None) -> tuple[CaseRevision, ChangeSet, ImpactSet]:
        self._require_case_org(case_id, organization_id)
        new_th = None if new_threshold is None else float(Decimal(str(new_threshold)))
        return self._store.create_revision(
            case_id=case_id, expected_parent=expected_parent,
            change_kind=change_kind, documents=documents, facts=facts,
            new_threshold=new_th,
        )

    def impact(self, case_id: str, revision_id: str) -> ImpactSet:
        return self._store.impact(case_id, revision_id)

    def resolve_issue(self, issue_id: str, organization_id: str, user_id: str,
                      role: str, revision_id: str, expected_bundle_hash: str,
                      decision_kind: str, rationale: str,
                      evidence_refs: list[str],
                      idempotency_key: str) -> dict:
        issue = self._store._issues.get(issue_id)  # noqa: SLF001
        if issue is None or self._case_org.get(issue.case_id) != organization_id:
            raise UnknownRevisionError(issue_id)
        return self._store.resolve_issue(
            issue_id=issue_id, revision_id=revision_id,
            expected_bundle_hash=expected_bundle_hash,
            decision_kind=decision_kind, rationale=rationale,
            evidence_refs=evidence_refs, idempotency_key=idempotency_key,
            actor=user_id,
        )

    def approve(self, case_id: str, organization_id: str, user_id: str,
                role: str, revision_id: str, package_hash: str,
                decision: str, reason: str,
                approved_ratio: str | None = None,
                approved_threshold: str | None = None,
                approved_comparator: str | None = None,
                approved_inputs: dict[str, str] | None = None,
                fresh_ratio: str | None = None,
                fresh_threshold: str | None = None,
                fresh_comparator: str | None = None,
                fresh_inputs: dict[str, str] | None = None) -> ApprovalBinding:
        self._require_case_org(case_id, organization_id)
        return self._store.approve(
            case_id=case_id, revision_id=revision_id, package_hash=package_hash,
            actor=user_id, role=role, decision=decision, reason=reason,  # type: ignore[arg-type]
            approved_ratio=approved_ratio, approved_threshold=approved_threshold,
            approved_comparator=approved_comparator, approved_inputs=approved_inputs,
            fresh_ratio=fresh_ratio, fresh_threshold=fresh_threshold,
            fresh_comparator=fresh_comparator, fresh_inputs=fresh_inputs,
        )

    def snapshot(self, case_id: str) -> dict:
        snap = self._store.snapshot(case_id)
        snap["organization_id"] = self._case_org.get(case_id)
        rev = snap["revision"]["revision_id"]
        snap["artifacts"] = _artifact_map(self.artifacts_for(case_id, rev))
        snap["covenant_rules"] = self._pipeline_rows("_rules", case_id, rev)
        snap["financial_facts"] = self._pipeline_rows("_facts", case_id, rev)
        return snap

    def append_event(self, case_id: str, organization_id: str,
                     revision_id: str | None, run_id: str | None,
                     event_type: str,
                     redacted_summary: dict | None = None) -> dict:
        self._require_case_org(case_id, organization_id)
        events = self._store._events.setdefault(case_id, [])  # noqa: SLF001
        seq = len(events) + 1
        event = {"sequence": seq, "name": event_type, "revision_id": revision_id,
                 "run_id": run_id, "summary": dict(redacted_summary or {}),
                 "created_at": datetime.now(timezone.utc).isoformat()}
        events.append(event)
        return event

    def list_events(self, case_id: str) -> list[dict]:
        return list(self._store._events.get(case_id, []))  # noqa: SLF001

    def get_case_org(self, case_id: str) -> str:
        try:
            self._store.current(case_id)
        except UnknownRevisionError:
            raise
        org = self._case_org.get(case_id)
        if org is None:
            raise UnknownRevisionError(case_id)
        return org

    def get_member_role(self, organization_id: str, user_id: str) -> str | None:
        return self._members.get((organization_id, user_id))

    def get_issue_case(self, issue_id: str) -> tuple[str, str, str]:
        issue = self._store._issues.get(issue_id)  # noqa: SLF001
        if issue is None:
            raise UnknownRevisionError(issue_id)
        org = self._case_org.get(issue.case_id)
        if org is None:
            raise UnknownRevisionError(issue_id)
        return issue.case_id, org, issue.revision_id

    def member_orgs(self, user_id: str) -> list[tuple[str, str]]:
        return [(org, role) for (org, uid), role in self._members.items()
                if uid == user_id]

    def _require_case_org(self, case_id: str, organization_id: str) -> None:
        if self._case_org.get(case_id, organization_id) != organization_id:
            raise UnknownRevisionError(case_id)


def configured_database_url() -> str | None:
    dsn = (os.getenv("DATABASE_URL", "") or os.getenv("SUPABASE_DB_URL", "")).strip()
    return dsn or None


def is_postgres_configured() -> bool:
    return configured_database_url() is not None


class PostgresRevisionRepository:
    """Transactional Postgres implementation using psycopg and DATABASE_URL."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        try:
            import psycopg  # type: ignore
        except Exception as error:
            raise RuntimeError("psycopg is required for PostgresRevisionRepository") from error
        self._psycopg = psycopg

    def verify(self) -> None:
        with self._psycopg.connect(self._dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1 from public.case_revisions limit 1")
                cur.execute("select 1 from public.review_issues limit 1")
                cur.execute("select 1 from public.approval_bindings limit 1")
                cur.execute("select 1 from public.domain_events limit 1")
                cur.execute("select 1 from public.case_snapshots limit 1")
                cur.execute("select 1 from public.revision_idempotency limit 1")

    def _connect(self):
        return self._psycopg.connect(self._dsn, autocommit=False)

    # -- mapping ------------------------------------------------------
    @staticmethod
    def _rev_from_row(row: Any) -> CaseRevision:
        (case_id, revision_id, parent, test_date, bundle, rulebook, mapping,
         calc, coverage, package, package_state, threshold, rule_id) = row
        return CaseRevision(
            case_id=case_id, revision_id=revision_id, parent_revision=parent,
            test_date=test_date.isoformat() if hasattr(test_date, "isoformat") else str(test_date),
            input_bundle_hash=bundle, rulebook_hash=rulebook, mapping_hash=mapping,
            calculation_hash=calc or "", coverage_hash=coverage or "",
            package_hash=package or "",
            status="superseded" if package_state == "superseded" else "current",
            threshold=str(threshold) if threshold is not None else "0.00",
            rule_id=rule_id or "",
        )

    # -- cases --------------------------------------------------------
    def ensure_case(self, case_id: str, organization_id: str, user_id: str,
                    test_date: str, rule_id: str, threshold: Any,
                    doc_ids: list[str], fact_keys: list[str], *,
                    name: str | None = None, borrower_name: str | None = None,
                    facility_name: str | None = None) -> CaseRevision:
        threshold_s = _money(threshold)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select organization_id from public.covenant_cases where id = %s",
                    (case_id,),
                )
                row = cur.fetchone()
                if row is None:
                    cur.execute(
                        "insert into public.covenant_cases"
                        " (id, organization_id, name, borrower_name, facility_name,"
                        " test_date, created_by) values"
                        " (%s, %s, %s, %s, %s, %s::date, %s)",
                        (case_id, organization_id, name or case_id,
                         borrower_name or "borrower", facility_name or "facility",
                         test_date, user_id),
                    )
                elif str(row[0]) != str(organization_id):
                    raise UnknownRevisionError(case_id)
                cur.execute(
                    "select case_id, revision_id, parent_revision_id, test_date,"
                    " input_bundle_hash, rulebook_hash, mapping_hash,"
                    " calculation_hash, coverage_hash, package_hash,"
                    " package_state, threshold, rule_id"
                    " from public.case_revisions where case_id = %s"
                    " order by created_at",
                    (case_id,),
                )
                existing = cur.fetchall()
                if existing:
                    conn.commit()
                    return self._rev_from_row(max(existing, key=lambda r: r[1]))
                bundle = stable_hash({"docs": sorted(doc_ids), "facts": sorted(fact_keys)})
                rulebook = stable_hash({"rule": rule_id, "threshold": threshold_s})
                mapping = stable_hash({"rule": rule_id, "facts": sorted(fact_keys)})
                calc = stable_hash({"rule": rule_id, "bundle": bundle})
                coverage = stable_hash({"scope": [rule_id]})
                package = stable_hash({"rev": "rev-1", "calc": calc})
                cur.execute(
                    "insert into public.case_revisions"
                    " (case_id, revision_id, organization_id, parent_revision_id,"
                    " test_date, input_bundle_hash, rulebook_hash, mapping_hash,"
                    " calculation_hash, coverage_hash, package_hash,"
                    " run_state, package_state, threshold, rule_id, created_by)"
                    " values (%s, 'rev-1', %s, null, %s::date, %s, %s, %s, %s, %s,"
                    " %s, 'waiting_review', 'draft', %s::numeric, %s, %s)",
                    (case_id, organization_id, test_date, bundle, rulebook,
                     mapping, calc, coverage, package, threshold_s, rule_id,
                     user_id),
                )
                import json as _json
                cur.execute(
                    "insert into public.case_snapshots"
                    " (organization_id, case_id, revision_id, snapshot, created_by)"
                    " values (%s, %s, 'rev-1', %s::jsonb, %s)"
                    " on conflict (case_id, revision_id) do nothing",
                    (organization_id, case_id,
                     _json.dumps({"documents": list(doc_ids), "facts": list(fact_keys),
                                  "threshold": threshold_s}), user_id),
                )
                cur.execute(
                    "insert into public.review_issues"
                    " (organization_id, case_id, revision_id, issue_kind, status,"
                    " expected_bundle_hash, external_issue_id)"
                    " values (%s, %s, 'rev-1', 'evidence_gap', 'open', %s, %s)"
                    " on conflict do nothing",
                    (organization_id, case_id, bundle, f"{case_id}-evidence-1"),
                )
                seq = self._next_sequence(cur, case_id, organization_id)
                cur.execute(
                    "insert into public.domain_events"
                    " (organization_id, case_id, revision_id, sequence, event_type,"
                    " redacted_summary) values (%s, %s, 'rev-1', %s, %s, %s::jsonb)",
                    (organization_id, case_id, seq, "REVISION_CREATED",
                     '{"revision_id": "rev-1"}'),
                )
                conn.commit()
                return CaseRevision(
                    case_id=case_id, revision_id="rev-1", parent_revision=None,
                    test_date=test_date, input_bundle_hash=bundle,
                    rulebook_hash=rulebook, mapping_hash=mapping,
                    calculation_hash=calc, coverage_hash=coverage,
                    package_hash=package, threshold=threshold_s, rule_id=rule_id,
                )

    def _head_row(self, cur: Any, case_id: str, organization_id: str) -> Any:
        cur.execute(
            "select case_id, revision_id, parent_revision_id, test_date,"
            " input_bundle_hash, rulebook_hash, mapping_hash,"
            " calculation_hash, coverage_hash, package_hash,"
            " package_state, threshold, rule_id"
            " from public.case_revisions"
            " where case_id = %s and organization_id = %s"
            " and package_state <> 'superseded'"
            " order by created_at desc limit 1 for update",
            (case_id, organization_id),
        )
        row = cur.fetchone()
        if row is None:
            # Distinguish unknown case (no rows at all) from tenant mismatch.
            cur.execute(
                "select 1 from public.case_revisions where case_id = %s limit 1",
                (case_id,),
            )
            if cur.fetchone() is None:
                raise UnknownRevisionError(case_id)
            raise UnknownRevisionError(case_id)
        return row

    def current(self, case_id: str) -> CaseRevision:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select case_id, revision_id, parent_revision_id, test_date,"
                    " input_bundle_hash, rulebook_hash, mapping_hash,"
                    " calculation_hash, coverage_hash, package_hash,"
                    " package_state, threshold, rule_id"
                    " from public.case_revisions where case_id = %s"
                    " order by created_at desc limit 1",
                    (case_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise UnknownRevisionError(case_id)
                return self._rev_from_row(row)

    def get(self, case_id: str, revision_id: str) -> CaseRevision:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select case_id, revision_id, parent_revision_id, test_date,"
                    " input_bundle_hash, rulebook_hash, mapping_hash,"
                    " calculation_hash, coverage_hash, package_hash,"
                    " package_state, threshold, rule_id"
                    " from public.case_revisions"
                    " where case_id = %s and revision_id = %s",
                    (case_id, revision_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise UnknownRevisionError(revision_id)
                return self._rev_from_row(row)

    def create_revision(self, case_id: str, organization_id: str, user_id: str,
                        expected_parent: str, change_kind: str,
                        documents: list[str], facts: list[str],
                        new_threshold: Any | None = None,
                        ) -> tuple[CaseRevision, ChangeSet, ImpactSet]:
        import json as _json
        with self._connect() as conn:
            with conn.cursor() as cur:
                head = self._head_row(cur, case_id, organization_id)
                (_, head_rev, _, head_test_date, _, _, _, _, _, _,
                 _, head_threshold, head_rule) = head
                if head_rev != expected_parent:
                    raise StaleCommandError(
                        f"expected parent {expected_parent} does not match current {head_rev}"
                    )
                cur.execute(
                    "select snapshot from public.case_snapshots"
                    " where case_id = %s and revision_id = %s",
                    (case_id, head_rev),
                )
                srow = cur.fetchone()
                if srow is None:
                    raise UnknownRevisionError(head_rev)
                prev_snap = srow[0] if isinstance(srow[0], dict) else _json.loads(srow[0])
                prev_docs = set(prev_snap.get("documents", []))
                prev_facts = set(prev_snap.get("facts", []))
                # Append-only document set (see RevisionStore.create_revision).
                new_docs = prev_docs | set(documents)
                new_facts = set(facts) if facts else prev_facts
                added = sorted(new_docs - prev_docs)
                replaced = sorted(d for d in documents if d in prev_docs)
                changed_facts = sorted(new_facts - prev_facts)
                threshold_s = _money(new_threshold) if new_threshold is not None else str(prev_snap["threshold"])
                threshold_changed = threshold_s != str(prev_snap["threshold"])
                # Next revision number.
                cur.execute(
                    "select revision_id from public.case_revisions where case_id = %s",
                    (case_id,),
                )
                nums = [int(r[0].split("-")[1]) for r in cur.fetchall()
                        if r[0].startswith("rev-") and r[0].split("-")[1].isdigit()]
                rev_id = f"rev-{max(nums) + 1}"
                bundle = stable_hash({"docs": sorted(new_docs), "facts": sorted(new_facts)})
                rulebook = stable_hash({"rule": head_rule, "threshold": threshold_s})
                mapping = stable_hash({"rule": head_rule, "facts": sorted(new_facts)})
                calc = stable_hash({"rule": head_rule, "bundle": bundle, "threshold": threshold_s})
                cur.execute(
                    "select coverage_hash from public.case_revisions"
                    " where case_id = %s and revision_id = %s",
                    (case_id, head_rev),
                )
                coverage = cur.fetchone()[0]
                package = stable_hash({"rev": rev_id, "calc": calc})
                test_date_s = head_test_date.isoformat() if hasattr(head_test_date, "isoformat") else str(head_test_date)
                cur.execute(
                    "update public.case_revisions set package_state = 'superseded'"
                    " where case_id = %s and revision_id = %s",
                    (case_id, head_rev),
                )
                cur.execute(
                    "insert into public.case_revisions"
                    " (case_id, revision_id, organization_id, parent_revision_id,"
                    " test_date, input_bundle_hash, rulebook_hash, mapping_hash,"
                    " calculation_hash, coverage_hash, package_hash,"
                    " run_state, package_state, threshold, rule_id, created_by)"
                    " values (%s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s,"
                    " %s, 'waiting_review', 'draft', %s::numeric, %s, %s)",
                    (case_id, rev_id, organization_id, head_rev, test_date_s,
                     bundle, rulebook, mapping, calc, coverage, package,
                     threshold_s, head_rule, user_id),
                )
                cur.execute(
                    "insert into public.case_snapshots"
                    " (organization_id, case_id, revision_id, snapshot, created_by)"
                    " values (%s, %s, %s, %s::jsonb, %s)",
                    (organization_id, case_id, rev_id,
                     _json.dumps({"documents": sorted(new_docs),
                                  "facts": sorted(new_facts),
                                  "threshold": threshold_s}), user_id),
                )
                affected = bool(added or replaced or changed_facts or threshold_changed)
                affected_rules = [head_rule] if affected else []
                cur.execute(
                    "insert into public.change_sets"
                    " (organization_id, case_id, source_revision_id,"
                    " target_revision_id, event_reason, change_kind,"
                    " added_documents, replaced_documents, changed_fact_keys,"
                    " created_by) values"
                    " (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (organization_id, case_id, head_rev, rev_id, change_kind,
                     change_kind, added, replaced, changed_facts, user_id),
                )
                cur.execute(
                    "select id from public.approval_bindings"
                    " where case_id = %s and organization_id = %s and superseded = false",
                    (case_id, organization_id),
                )
                prior_approvals = cur.fetchall()
                invalidated = [head_rev] if prior_approvals else []
                changed_defs = (["leverage-threshold"] if threshold_changed
                                else ([f"doc:{d}" for d in added + replaced]
                                      or [f"fact:{f}" for f in changed_facts]))
                stale = [f"artifact:{head_rev}:certificate"] if affected_rules else []
                cur.execute(
                    "insert into public.impact_sets"
                    " (organization_id, case_id, revision_id,"
                    " changed_definition_ids, affected_rule_ids,"
                    " affected_fact_keys, dependent_calculations,"
                    " invalidated_decision_refs, stale_artifact_refs,"
                    " unaffected_references, review_requirements)"
                    " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
                    (organization_id, case_id, rev_id, changed_defs,
                     affected_rules, changed_facts,
                     [f"calc:{head_rule}"] if affected_rules else [],
                     invalidated,
                     stale,
                     sorted(prev_docs & new_docs - set(replaced)),
                     _json.dumps(["officer-review"] if affected_rules else [])),
                )
                # Approvals are append-only: old bindings stay immutable and are
                # treated as superseded by the read model (target != head).
                # The approve() head check makes them unable to authorize a
                # new package without mutating history.
                cur.execute(
                    "update public.review_issues set status = 'superseded'"
                    " where case_id = %s and organization_id = %s and status = 'open'",
                    (case_id, organization_id),
                )
                cur.execute(
                    "insert into public.review_issues"
                    " (organization_id, case_id, revision_id, issue_kind, status,"
                    " expected_bundle_hash, external_issue_id)"
                    " values (%s, %s, %s, 'evidence_gap', 'open', %s, %s)",
                    (organization_id, case_id, rev_id, bundle,
                     f"{case_id}-{rev_id}-evidence-1"),
                )
                seq = self._next_sequence(cur, case_id, organization_id)
                for name in ("INPUT_CHANGED", "RESULT_INVALIDATED"):
                    seq += 1 if name != "INPUT_CHANGED" else 0
                    cur.execute(
                        "insert into public.domain_events"
                        " (organization_id, case_id, revision_id, sequence,"
                        " event_type, redacted_summary)"
                        " values (%s, %s, %s, %s, %s, %s::jsonb)",
                        (organization_id, case_id, rev_id, seq, name,
                         _json.dumps({"revision_id": rev_id})),
                    )
                conn.commit()
                rev = CaseRevision(
                    case_id=case_id, revision_id=rev_id, parent_revision=head_rev,
                    test_date=test_date_s, input_bundle_hash=bundle,
                    rulebook_hash=rulebook, mapping_hash=mapping,
                    calculation_hash=calc, coverage_hash=coverage or "",
                    package_hash=package, threshold=threshold_s,
                    rule_id=head_rule or "",
                )
                changeset = ChangeSet(
                    source_revision=head_rev, target_revision=rev_id,
                    added_documents=added, replaced_documents=replaced,
                    changed_fact_ids=changed_facts, event_reason=change_kind,
                )
                impact = ImpactSet(
                    changed_definitions=changed_defs,
                    affected_rule_ids=affected_rules,
                    affected_fact_keys=changed_facts,
                    dependent_calculations=[f"calc:{head_rule}"] if affected_rules else [],
                    invalidated_decision_ids=invalidated,
                    stale_artifact_ids=stale,
                    unaffected_references=sorted(prev_docs & new_docs - set(replaced)),
                    review_requirements=(["officer-review"] if affected_rules else []),
                )
                return rev, changeset, impact

    def impact(self, case_id: str, revision_id: str) -> ImpactSet:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select changed_definition_ids, affected_rule_ids,"
                    " affected_fact_keys, dependent_calculations,"
                    " invalidated_decision_refs, stale_artifact_refs,"
                    " unaffected_references, review_requirements"
                    " from public.impact_sets"
                    " where case_id = %s and revision_id = %s",
                    (case_id, revision_id),
                )
                row = cur.fetchone()
                if row is not None:
                    import json as _json
                    req = row[7]
                    if isinstance(req, str):
                        req = _json.loads(req)
                    return ImpactSet(
                        changed_definitions=list(row[0] or []),
                        affected_rule_ids=list(row[1] or []),
                        affected_fact_keys=list(row[2] or []),
                        dependent_calculations=list(row[3] or []),
                        invalidated_decision_ids=list(row[4] or []),
                        stale_artifact_ids=list(row[5] or []),
                        unaffected_references=list(row[6] or []),
                        review_requirements=list(req or []),
                    )
                cur.execute(
                    "select 1 from public.case_revisions"
                    " where case_id = %s and revision_id = %s",
                    (case_id, revision_id),
                )
                if cur.fetchone() is None:
                    raise UnknownRevisionError(revision_id)
                return ImpactSet()

    def resolve_issue(self, issue_id: str, organization_id: str, user_id: str,
                      role: str, revision_id: str, expected_bundle_hash: str,
                      decision_kind: str, rationale: str,
                      evidence_refs: list[str],
                      idempotency_key: str) -> dict:
        import json as _json
        payload = {"issue_id": issue_id, "revision_id": revision_id,
                   "expected_bundle_hash": expected_bundle_hash,
                   "decision_kind": decision_kind, "rationale": rationale,
                   "evidence_refs": evidence_refs,
                   "actor": user_id, "role": role}
        request_hash = stable_hash(payload)
        response = {"issue_id": issue_id, "revision_id": revision_id,
                    "status": "resolved", "decision_kind": decision_kind}
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select request_hash, response from public.revision_idempotency"
                    " where organization_id = %s and idempotency_key = %s for update",
                    (organization_id, idempotency_key),
                )
                prior = cur.fetchone()
                if prior is not None:
                    if prior[0] == request_hash:
                        stored = prior[1]
                        conn.commit()
                        return stored if isinstance(stored, dict) else _json.loads(stored)
                    raise IdempotencyConflictError(
                        "idempotency key reused with different payload")
                cur.execute(
                    "select id, case_id, revision_id, status, expected_bundle_hash"
                    " from public.review_issues"
                    " where external_issue_id = %s and organization_id = %s for update",
                    (issue_id, organization_id),
                )
                issue = cur.fetchone()
                if issue is None:
                    raise UnknownRevisionError(issue_id)
                issue_uuid, issue_case, issue_rev, status, bundle = issue
                head = self._head_row(cur, issue_case, organization_id)
                head_rev = head[1]
                head_bundle = head[4]
                if revision_id != head_rev or revision_id != issue_rev:
                    raise StaleCommandError("issue revision is stale")
                if expected_bundle_hash != head_bundle:
                    raise StaleCommandError("bundle hash no longer matches current state")
                if not rationale:
                    raise ValueError("rationale is required")
                cur.execute(
                    "update public.review_issues set status = 'resolved',"
                    " resolved_at = now(), resolved_by = %s,"
                    " decision_kind = %s, rationale = %s, evidence_refs = %s::jsonb"
                    " where id = %s",
                    (user_id, decision_kind, rationale,
                     _json.dumps(list(evidence_refs)), issue_uuid),
                )
                cur.execute(
                    "update public.case_revisions set package_state = 'ready_for_officer_review'"
                    " where case_id = %s and revision_id = %s and package_state = 'draft'"
                    " and not exists (select 1 from public.review_issues"
                    "   where case_id = %s and revision_id = %s and status = 'open')",
                    (issue_case, revision_id, issue_case, revision_id),
                )
                cur.execute(
                    "insert into public.review_decisions"
                    " (organization_id, issue_id, case_id, revision_id, actor_id,"
                    " actor_role, decision_kind, rationale, evidence_refs,"
                    " idempotency_key, request_hash, response)"
                    " values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)",
                    (organization_id, issue_uuid, issue_case, revision_id,
                     user_id, role, decision_kind, rationale,
                     _json.dumps(list(evidence_refs)), idempotency_key,
                     request_hash, _json.dumps(response)),
                )
                cur.execute(
                    "insert into public.revision_idempotency"
                    " (organization_id, idempotency_key, request_hash, response)"
                    " values (%s, %s, %s, %s::jsonb)",
                    (organization_id, idempotency_key, request_hash,
                     _json.dumps(response)),
                )
                seq = self._next_sequence(cur, issue_case, organization_id)
                cur.execute(
                    "insert into public.domain_events"
                    " (organization_id, case_id, revision_id, sequence,"
                    " event_type, redacted_summary)"
                    " values (%s, %s, %s, %s, 'REVIEW_RESOLVED', %s::jsonb)",
                    (organization_id, issue_case, revision_id, seq,
                     _json.dumps({"revision_id": revision_id})),
                )
                conn.commit()
                return response

    def approve(self, case_id: str, organization_id: str, user_id: str,
                role: str, revision_id: str, package_hash: str,
                decision: str, reason: str,
                approved_ratio: str | None = None,
                approved_threshold: str | None = None,
                approved_comparator: str | None = None,
                approved_inputs: dict[str, str] | None = None,
                fresh_ratio: str | None = None,
                fresh_threshold: str | None = None,
                fresh_comparator: str | None = None,
                fresh_inputs: dict[str, str] | None = None) -> ApprovalBinding:
        import json as _json
        with self._connect() as conn:
            with conn.cursor() as cur:
                head = self._head_row(cur, case_id, organization_id)
                head_rev = head[1]
                head_bundle = head[4]
                head_package = head[9]
                if revision_id != head_rev:
                    raise StaleCommandError("approval targets a superseded revision")
                if package_hash != head_package:
                    raise StaleCommandError("package hash no longer matches current state")
                # Append-only approvals: currency is determined by targeting the
                # exact current head, checked above. History is never mutated.
                RevisionStore._check_number_drift(  # noqa: SLF001
                    approved_ratio, approved_threshold, approved_comparator,
                    approved_inputs, fresh_ratio, fresh_threshold,
                    fresh_comparator, fresh_inputs)
                cur.execute(
                    "select 1 from public.review_issues"
                    " where case_id = %s and organization_id = %s"
                    " and revision_id = %s and status = 'open' limit 1",
                    (case_id, organization_id, revision_id),
                )
                blocking = cur.fetchone() is not None
                if blocking and decision == "approved":
                    raise StaleCommandError("blocking review issues remain open")
                if not reason:
                    raise ValueError("reason is required")
                ratio = fresh_ratio if fresh_ratio is not None else approved_ratio
                threshold = fresh_threshold if fresh_threshold is not None else approved_threshold
                comparator = fresh_comparator if fresh_comparator is not None else approved_comparator
                inputs = dict(fresh_inputs) if fresh_inputs is not None else dict(approved_inputs or {})
                if decision == "approved" and (
                        ratio is None or threshold is None or comparator is None or not inputs):
                    raise ValueError("approved numbers and inputs are required")
                cur.execute(
                    "select id from public.approval_bindings"
                    " where case_id = %s and organization_id = %s and superseded = false"
                    " order by created_at desc limit 1",
                    (case_id, organization_id),
                )
                prow = cur.fetchone()
                supersedes = prow[0] if prow else None
                cur.execute(
                    "insert into public.approval_bindings"
                    " (organization_id, case_id, revision_id, actor_id, actor_role,"
                    " decision, reason, package_hash, approved_ratio,"
                    " approved_threshold, approved_comparator, approved_inputs,"
                    " bundle_hash, supersedes_approval_id)"
                    " values (%s, %s, %s, %s, %s, %s, %s, %s,"
                    " %s::numeric, %s::numeric, %s, %s::jsonb, %s, %s)"
                    " returning id, created_at",
                    (organization_id, case_id, revision_id, user_id, role,
                     decision, reason, package_hash, ratio, threshold,
                     comparator, _json.dumps(inputs), head_bundle, supersedes),
                )
                new_id, created_at = cur.fetchone()
                if decision == "approved":
                    cur.execute(
                        "update public.case_revisions set package_state = 'approved_draft'"
                        " where case_id = %s and revision_id = %s",
                        (case_id, revision_id),
                    )
                seq = self._next_sequence(cur, case_id, organization_id)
                cur.execute(
                    "insert into public.domain_events"
                    " (organization_id, case_id, revision_id, sequence,"
                    " event_type, redacted_summary)"
                    " values (%s, %s, %s, %s, 'APPROVAL_RECORDED', %s::jsonb)",
                    (organization_id, case_id, revision_id, seq,
                     _json.dumps({"revision_id": revision_id})),
                )
                conn.commit()
                return ApprovalBinding(
                    actor=user_id, role=role, case_id=case_id,
                    target_revision=revision_id, bundle_hash=head_bundle,
                    package_hash=package_hash, decision=decision,  # type: ignore[arg-type]
                    reason=reason, timestamp=created_at,
                    approved_ratio=ratio, approved_threshold=threshold,
                    approved_comparator=comparator, approved_inputs=inputs,
                )

    def snapshot(self, case_id: str) -> dict:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select case_id, revision_id, parent_revision_id, test_date,"
                    " input_bundle_hash, rulebook_hash, mapping_hash,"
                    " calculation_hash, coverage_hash, package_hash,"
                    " package_state, threshold, rule_id, organization_id, run_state"
                    " from public.case_revisions where case_id = %s"
                    " order by created_at desc limit 1",
                    (case_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise UnknownRevisionError(case_id)
                org = str(row[13])
                head = self._rev_from_row(row[:13])
                rev = head.revision_id
                cur.execute(
                    "select snapshot from public.case_snapshots"
                    " where case_id = %s and revision_id = %s",
                    (case_id, rev),
                )
                srow = cur.fetchone()
                snap = _jsonb(srow[0], {}) if srow else {}
                cur.execute(
                    "select actor_id, actor_role, revision_id, package_hash, decision,"
                    " reason, created_at, approved_ratio, approved_threshold,"
                    " approved_comparator, approved_inputs, superseded"
                    " from public.approval_bindings"
                    " where case_id = %s and organization_id = %s order by created_at",
                    (case_id, org),
                )
                approvals = []
                for a in cur.fetchall():
                    approvals.append({
                        "actor": str(a[0]), "role": a[1], "case_id": case_id,
                        "target_revision": a[2], "package_hash": a[3],
                        "decision": a[4], "reason": a[5],
                        "timestamp": a[6].isoformat() if hasattr(a[6], "isoformat") else str(a[6]),
                        "approved_ratio": str(a[7]) if a[7] is not None else None,
                        "approved_threshold": str(a[8]) if a[8] is not None else None,
                        "approved_comparator": a[9],
                        "approved_inputs": _jsonb(a[10], {}),
                        # Append-only read model: anything not targeting the
                        # head is historical.
                        "superseded": bool(a[2] != rev),
                    })
                cur.execute(
                    "select external_issue_id, status, issue_kind, decision_kind,"
                    " rationale, resolved_by, resolved_at from public.review_issues"
                    " where case_id = %s and organization_id = %s and revision_id = %s"
                    " order by created_at",
                    (case_id, org, rev),
                )
                issues = [issue_view(*r) for r in cur.fetchall()]
                open_issues = sum(1 for i in issues if i["status"] == "open")
                cur.execute(
                    "select external_rule_id, covenant_type, support_state, comparator,"
                    " threshold, measurement_period, structured_rule, source_spans"
                    " from public.covenant_rules where case_id = %s and revision_id = %s"
                    " order by external_rule_id",
                    (case_id, rev),
                )
                rules = [{
                    "external_rule_id": r[0], "covenant_type": r[1],
                    "support_state": r[2], "comparator": r[3],
                    "threshold": _money(r[4]) if r[4] is not None else None,
                    "measurement_period": r[5],
                    "structured_rule": _jsonb(r[6], {}),
                    "source_spans": _jsonb(r[7], []),
                } for r in cur.fetchall()]
                cur.execute(
                    "select fact_key, amount, currency, unit_scale, period_start,"
                    " period_end, evidence_state, source_spans"
                    " from public.financial_facts where case_id = %s and revision_id = %s"
                    " order by fact_key",
                    (case_id, rev),
                )
                facts = [{
                    "fact_key": r[0],
                    "amount": _money(r[1]) if r[1] is not None else None,
                    "currency": r[2], "unit_scale": int(r[3]),
                    "period_start": r[4].isoformat() if r[4] is not None else None,
                    "period_end": r[5].isoformat() if r[5] is not None else None,
                    "evidence_state": r[6],
                    "source_spans": _jsonb(r[7], []),
                } for r in cur.fetchall()]
                artifacts = _artifact_map(self._artifact_rows(cur, case_id, rev))
                cur.execute(
                    "select max(sequence) from public.domain_events where case_id = %s",
                    (case_id,),
                )
                last = cur.fetchone()[0]
                return {
                    "case_id": case_id,
                    "organization_id": org,
                    "revision": head.model_dump(mode="json"),
                    # Stored columns, not derived from issue counts.
                    "run_state": row[14],
                    "per_covenant_results": [
                        {"rule_id": head.rule_id, "threshold": head.threshold,
                         "status": "stale" if open_issues else "current"}
                    ],
                    "coverage": {"state": "complete_for_declared_scope",
                                 "hash": head.coverage_hash},
                    "package_state": row[10],
                    "package_hash": head.package_hash,
                    "open_review_issues": open_issues,
                    "review_issues": issues,
                    "documents": list(snap.get("documents", [])),
                    "artifacts": artifacts,
                    "covenant_rules": rules,
                    "financial_facts": facts,
                    "approvals": approvals,
                    "last_event_sequence": int(last or 0),
                }

    @staticmethod
    def _artifact_rows(cur: Any, case_id: str, revision_id: str) -> list[dict]:
        cur.execute(
            "select artifact_type, content_hash, payload from public.artifacts"
            " where case_id = %s and revision_id = %s and state = 'current'"
            " order by artifact_type",
            (case_id, revision_id),
        )
        return [{"artifact_type": r[0], "content_hash": r[1],
                 "payload": _jsonb(r[2], {})} for r in cur.fetchall()]

    def artifacts_for(self, case_id: str, revision_id: str) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                return self._artifact_rows(cur, case_id, revision_id)

    def set_run_state(self, case_id: str, revision_id: str, state: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update public.case_revisions set run_state = %s"
                    " where case_id = %s and revision_id = %s",
                    (state, case_id, revision_id),
                )
            conn.commit()

    def append_event(self, case_id: str, organization_id: str,
                     revision_id: str | None, run_id: str | None,
                     event_type: str,
                     redacted_summary: dict | None = None) -> dict:
        import json as _json
        with self._connect() as conn:
            with conn.cursor() as cur:
                seq = self._next_sequence(cur, case_id, organization_id)
                cur.execute(
                    "insert into public.domain_events"
                    " (organization_id, case_id, revision_id, run_id, sequence,"
                    " event_type, redacted_summary)"
                    " values (%s, %s, %s, %s, %s, %s, %s::jsonb)"
                    " returning sequence",
                    (organization_id, case_id, revision_id, run_id, seq,
                     event_type, _json.dumps(dict(redacted_summary or {}))),
                )
                conn.commit()
                return {"sequence": seq, "name": event_type,
                        "revision_id": revision_id, "run_id": run_id}

    def list_events(self, case_id: str) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select sequence, event_type, revision_id, run_id,"
                    " redacted_summary, created_at from public.domain_events"
                    " where case_id = %s order by sequence",
                    (case_id,),
                )
                out = []
                for seq, etype, rev, run, summary, created in cur.fetchall():
                    out.append({"sequence": int(seq), "name": etype,
                                "revision_id": rev, "run_id": run,
                                "summary": summary if isinstance(summary, dict) else {},
                                "created_at": created.isoformat() if created else None})
                return out

    def get_case_org(self, case_id: str) -> str:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select organization_id from public.covenant_cases where id = %s",
                    (case_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise UnknownRevisionError(case_id)
                return str(row[0])

    def get_member_role(self, organization_id: str, user_id: str) -> str | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select role from public.organization_members"
                    " where organization_id = %s and user_id = %s",
                    (organization_id, user_id),
                )
                row = cur.fetchone()
                return row[0] if row else None

    def get_issue_case(self, issue_id: str) -> tuple[str, str, str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select case_id, organization_id, revision_id"
                    " from public.review_issues where external_issue_id = %s",
                    (issue_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise UnknownRevisionError(issue_id)
                return row[0], str(row[1]), row[2]

    def member_orgs(self, user_id: str) -> list[tuple[str, str]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select organization_id, role from public.organization_members"
                    " where user_id = %s order by created_at",
                    (user_id,),
                )
                return [(str(r[0]), r[1]) for r in cur.fetchall()]

    @staticmethod
    def _next_sequence(cur: Any, case_id: str, organization_id: str) -> int:
        cur.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"events:{case_id}",))
        cur.execute(
            "select coalesce(max(sequence), 0) + 1 from public.domain_events"
            " where case_id = %s",
            (case_id,),
        )
        return int(cur.fetchone()[0])


def revision_repository_from_env() -> MemoryRevisionRepository | PostgresRevisionRepository:
    """Return Postgres when a database URL is configured, else memory.

    A configured but unusable database raises; callers must fail readiness
    rather than silently downgrading to memory.
    """
    from src.platform.jobqueue import DurabilityConfigurationError

    dsn = configured_database_url()
    if not dsn:
        return MemoryRevisionRepository()
    try:
        repo = PostgresRevisionRepository(dsn)
        repo.verify()
        return repo
    except Exception as error:
        raise DurabilityConfigurationError(
            "Configured revision database is unavailable; refusing memory fallback"
        ) from error
