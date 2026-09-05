"""Change-aware revisioning: immutable revisions, impacts, approvals.

Implements the contract's "Change-aware rechecking" section with an
in-memory store (production replaces it with Supabase/Postgres).
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Literal

from pydantic import BaseModel, Field

from .domain import money_str
from .hashing import stable_hash


class CaseRevision(BaseModel):
    case_id: str
    revision_id: str
    parent_revision: str | None = None
    test_date: str
    input_bundle_hash: str
    rulebook_hash: str
    mapping_hash: str
    calculation_hash: str
    coverage_hash: str
    package_hash: str
    status: Literal["current", "superseded"] = "current"
    threshold: str
    rule_id: str


class ChangeSet(BaseModel):
    source_revision: str
    target_revision: str
    added_documents: list[str] = Field(default_factory=list)
    replaced_documents: list[str] = Field(default_factory=list)
    changed_fact_ids: list[str] = Field(default_factory=list)
    changed_decision_ids: list[str] = Field(default_factory=list)
    event_reason: str


class ImpactSet(BaseModel):
    changed_definitions: list[str] = Field(default_factory=list)
    affected_rule_ids: list[str] = Field(default_factory=list)
    affected_fact_keys: list[str] = Field(default_factory=list)
    dependent_calculations: list[str] = Field(default_factory=list)
    invalidated_decision_ids: list[str] = Field(default_factory=list)
    stale_artifact_ids: list[str] = Field(default_factory=list)
    unaffected_references: list[str] = Field(default_factory=list)
    review_requirements: list[str] = Field(default_factory=list)


class ApprovalBinding(BaseModel):
    actor: str
    role: str
    case_id: str
    target_revision: str
    bundle_hash: str
    package_hash: str
    decision: Literal["approved", "rejected"]
    reason: str
    timestamp: datetime
    superseding_approval_ref: str | None = None
    superseded: bool = False
    # Exact approved numeric snapshot (money_str exact-string decimals, never floats).
    approved_ratio: str | None = None
    approved_threshold: str | None = None
    approved_comparator: str | None = None
    approved_inputs: dict[str, str] = Field(default_factory=dict)

    def locked_summary(self) -> str:
        """Human-readable lock statement for frontend / audit reports."""
        bits = [
            f"revision {self.target_revision}",
            f"ratio {self.approved_ratio}" if self.approved_ratio is not None else "ratio n/a",
            f"threshold {self.approved_comparator or '<='} {self.approved_threshold}"
            if self.approved_threshold is not None
            else "threshold n/a",
        ]
        if self.approved_inputs:
            inputs = ", ".join(f"{k}={v}" for k, v in sorted(self.approved_inputs.items()))
            bits.append(f"inputs {inputs}")
        return f"this approval locked in: {'; '.join(bits)}"


class ReviewIssueRecord(BaseModel):
    issue_id: str
    case_id: str
    revision_id: str
    bundle_hash: str
    status: Literal["open", "resolved"] = "open"
    decision_kind: str | None = None
    rationale: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    resolved_by: str | None = None
    resolved_at: datetime | None = None


class StaleCommandError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass


class UnknownRevisionError(LookupError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RevisionStore:
    """Thread-safe in-memory revision/approval/idempotency store."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._revisions: dict[str, dict[str, CaseRevision]] = {}
        self._changes: dict[str, ChangeSet] = {}
        self._impacts: dict[str, ImpactSet] = {}
        self._approvals: dict[str, list[ApprovalBinding]] = {}
        self._issues: dict[str, ReviewIssueRecord] = {}
        self._idempotency: dict[str, dict] = {}
        self._events: dict[str, list[dict]] = {}
        self._counters: dict[str, int] = {}
        self._snapshots: dict[str, dict[str, dict]] = {}

    # -- seeding ---------------------------------------------------------
    def ensure_case(
        self,
        case_id: str,
        test_date: str,
        rule_id: str,
        threshold: float,
        doc_ids: list[str],
        fact_keys: list[str],
    ) -> CaseRevision:
        with self._lock:
            existing = self._revisions.get(case_id, {})
            if existing:
                return existing[max(existing)]
            bundle = stable_hash({"docs": sorted(doc_ids), "facts": sorted(fact_keys)})
            rulebook = stable_hash({"rule": rule_id, "threshold": money_str(threshold)})
            mapping = stable_hash({"rule": rule_id, "facts": sorted(fact_keys)})
            calc = stable_hash({"rule": rule_id, "bundle": bundle})
            coverage = stable_hash({"scope": [rule_id]})
            rev = CaseRevision(
                case_id=case_id,
                revision_id="rev-1",
                parent_revision=None,
                test_date=test_date,
                input_bundle_hash=bundle,
                rulebook_hash=rulebook,
                mapping_hash=mapping,
                calculation_hash=calc,
                coverage_hash=coverage,
                package_hash=stable_hash({"rev": "rev-1", "calc": calc}),
                threshold=money_str(threshold),
                rule_id=rule_id,
            )
            self._revisions[case_id] = {"rev-1": rev}
            self._counters[case_id] = 1
            self._snapshots.setdefault(case_id, {})["rev-1"] = {
                "documents": list(doc_ids),
                "facts": list(fact_keys),
                "threshold": money_str(threshold),
            }
            self._events.setdefault(case_id, []).append(
                {"sequence": 1, "name": "REVISION_CREATED", "revision_id": "rev-1"}
            )
            # Seed one open blocking review issue for the resolve flow.
            issue_id = f"{case_id}-evidence-1"
            self._issues[issue_id] = ReviewIssueRecord(
                issue_id=issue_id,
                case_id=case_id,
                revision_id="rev-1",
                bundle_hash=bundle,
            )
            return rev

    def current(self, case_id: str) -> CaseRevision:
        with self._lock:
            revs = self._revisions.get(case_id)
            if not revs:
                raise UnknownRevisionError(case_id)
            return revs[max(revs)]

    def get(self, case_id: str, revision_id: str) -> CaseRevision:
        with self._lock:
            try:
                return self._revisions[case_id][revision_id]
            except KeyError as error:
                raise UnknownRevisionError(revision_id) from error

    # -- revisions --------------------------------------------------------
    def create_revision(
        self,
        case_id: str,
        expected_parent: str,
        change_kind: str,
        documents: list[str],
        facts: list[str],
        new_threshold: float | None = None,
    ) -> tuple[CaseRevision, ChangeSet, ImpactSet]:
        with self._lock:
            revs = self._revisions.get(case_id)
            if not revs:
                raise UnknownRevisionError(case_id)
            head = revs[max(revs)]
            if head.revision_id != expected_parent:
                raise StaleCommandError(
                    f"expected parent {expected_parent} does not match current {head.revision_id}"
                )
            prev_snap = self._snapshots[case_id][head.revision_id]
            prev_docs = set(prev_snap["documents"])
            prev_facts = set(prev_snap["facts"])
            new_docs = set(documents) if documents else prev_docs
            new_facts = set(facts) if facts else prev_facts
            added = sorted(new_docs - prev_docs)
            replaced = sorted(d for d in documents if d in prev_docs) if documents else []
            changed_facts = sorted(new_facts - prev_facts)
            threshold_str = money_str(new_threshold) if new_threshold is not None else prev_snap["threshold"]
            threshold_changed = threshold_str != prev_snap["threshold"]

            self._counters[case_id] += 1
            rev_id = f"rev-{self._counters[case_id]}"
            bundle = stable_hash({"docs": sorted(new_docs), "facts": sorted(new_facts)})
            rulebook = stable_hash({"rule": head.rule_id, "threshold": threshold_str})
            mapping = stable_hash({"rule": head.rule_id, "facts": sorted(new_facts)})
            calc = stable_hash({"rule": head.rule_id, "bundle": bundle, "threshold": threshold_str})
            coverage = head.coverage_hash
            new_rev = CaseRevision(
                case_id=case_id,
                revision_id=rev_id,
                parent_revision=head.revision_id,
                test_date=head.test_date,
                input_bundle_hash=bundle,
                rulebook_hash=rulebook,
                mapping_hash=mapping,
                calculation_hash=calc,
                coverage_hash=coverage,
                package_hash=stable_hash({"rev": rev_id, "calc": calc}),
                threshold=threshold_str,
                rule_id=head.rule_id,
            )
            head.status = "superseded"
            revs[rev_id] = new_rev
            self._snapshots[case_id][rev_id] = {
                "documents": sorted(new_docs),
                "facts": sorted(new_facts),
                "threshold": threshold_str,
            }
            changeset = ChangeSet(
                source_revision=head.revision_id,
                target_revision=rev_id,
                added_documents=added,
                replaced_documents=replaced,
                changed_fact_ids=changed_facts,
                event_reason=change_kind,
            )
            affected_rules = [head.rule_id] if (added or replaced or changed_facts or threshold_changed) else []
            impact = ImpactSet(
                changed_definitions=["leverage-threshold"] if threshold_changed else ([f"doc:{d}" for d in added + replaced] or [f"fact:{f}" for f in changed_facts]),
                affected_rule_ids=affected_rules,
                affected_fact_keys=changed_facts,
                dependent_calculations=[f"calc:{head.rule_id}"] if affected_rules else [],
                invalidated_decision_ids=[a.target_revision for a in self._approvals.get(case_id, []) if not a.superseded],
                stale_artifact_ids=[f"artifact:{head.revision_id}:certificate"] if affected_rules else [],
                unaffected_references=sorted(prev_docs & new_docs - set(replaced)),
                review_requirements=(["officer-review"] if affected_rules else []),
            )
            self._changes[rev_id] = changeset
            self._impacts[rev_id] = impact
            for approval in self._approvals.get(case_id, []):
                approval.superseded = True
            seq = len(self._events[case_id]) + 1
            self._events[case_id].append(
                {"sequence": seq, "name": "INPUT_CHANGED", "revision_id": rev_id}
            )
            self._events[case_id].append(
                {"sequence": seq + 1, "name": "RESULT_INVALIDATED", "revision_id": rev_id}
            )
            # New revision opens a fresh review issue.
            self._issues[f"{case_id}-{rev_id}-evidence-1"] = ReviewIssueRecord(
                issue_id=f"{case_id}-{rev_id}-evidence-1",
                case_id=case_id,
                revision_id=rev_id,
                bundle_hash=bundle,
            )
            return new_rev, changeset, impact

    def impact(self, case_id: str, revision_id: str) -> ImpactSet:
        with self._lock:
            if revision_id in self._impacts:
                return self._impacts[revision_id]
            self.get(case_id, revision_id)  # raises if unknown
            return ImpactSet()

    # -- review issues ----------------------------------------------------
    def resolve_issue(
        self,
        issue_id: str,
        revision_id: str,
        expected_bundle_hash: str,
        decision_kind: str,
        rationale: str,
        evidence_refs: list[str],
        idempotency_key: str,
        actor: str,
    ) -> dict:
        with self._lock:
            payload = {
                "issue_id": issue_id,
                "revision_id": revision_id,
                "expected_bundle_hash": expected_bundle_hash,
                "decision_kind": decision_kind,
                "rationale": rationale,
                "evidence_refs": evidence_refs,
            }
            if idempotency_key in self._idempotency:
                original = self._idempotency[idempotency_key]
                if original["payload"] == payload:
                    return original["response"]
                raise IdempotencyConflictError("idempotency key reused with different payload")
            issue = self._issues.get(issue_id)
            if issue is None:
                raise UnknownRevisionError(issue_id)
            head = self.current(issue.case_id)
            if revision_id != head.revision_id or revision_id != issue.revision_id:
                raise StaleCommandError("issue revision is stale")
            if expected_bundle_hash != head.input_bundle_hash:
                raise StaleCommandError("bundle hash no longer matches current state")
            if not rationale:
                raise ValueError("rationale is required")
            issue.status = "resolved"
            issue.decision_kind = decision_kind
            issue.rationale = rationale
            issue.evidence_refs = list(evidence_refs)
            issue.resolved_by = actor
            issue.resolved_at = _now()
            response = {
                "issue_id": issue_id,
                "revision_id": revision_id,
                "status": "resolved",
                "decision_kind": decision_kind,
            }
            self._idempotency[idempotency_key] = {"payload": payload, "response": response}
            seq = len(self._events.get(issue.case_id, [])) + 1
            self._events.setdefault(issue.case_id, []).append(
                {"sequence": seq, "name": "REVIEW_RESOLVED", "revision_id": revision_id}
            )
            return response

    @staticmethod
    def _check_number_drift(
        approved_ratio: str | None,
        approved_threshold: str | None,
        approved_comparator: str | None,
        approved_inputs: dict[str, str] | None,
        fresh_ratio: str | None,
        fresh_threshold: str | None,
        fresh_comparator: str | None,
        fresh_inputs: dict[str, str] | None,
    ) -> None:
        """Reject when an officer-seen number differs from fresh recalculation.

        Each mismatch names the specific number that drifted, e.g.
        'threshold changed from 3.75 to 3.25'. Fields the caller did not
        submit (None) are not compared; fresh values are authoritative.
        """
        if fresh_ratio is None:
            return
        if approved_ratio is not None and approved_ratio != fresh_ratio:
            raise StaleCommandError(f"ratio changed from {approved_ratio} to {fresh_ratio}")
        if approved_threshold is not None and approved_threshold != fresh_threshold:
            raise StaleCommandError(
                f"threshold changed from {approved_threshold} to {fresh_threshold}"
            )
        if approved_comparator is not None and approved_comparator != fresh_comparator:
            raise StaleCommandError(
                f"comparator changed from {approved_comparator} to {fresh_comparator}"
            )
        for key, seen in (approved_inputs or {}).items():
            current = (fresh_inputs or {}).get(key)
            if current is not None and seen != current:
                raise StaleCommandError(f"input {key} changed from {seen} to {current}")

    # -- approvals ----------------------------------------------------------
    def approve(
        self,
        case_id: str,
        revision_id: str,
        package_hash: str,
        actor: str,
        role: str,
        decision: Literal["approved", "rejected"],
        reason: str,
        approved_ratio: str | None = None,
        approved_threshold: str | None = None,
        approved_comparator: str | None = None,
        approved_inputs: dict[str, str] | None = None,
        fresh_ratio: str | None = None,
        fresh_threshold: str | None = None,
        fresh_comparator: str | None = None,
        fresh_inputs: dict[str, str] | None = None,
    ) -> ApprovalBinding:
        with self._lock:
            head = self.current(case_id)
            if revision_id != head.revision_id:
                raise StaleCommandError("approval targets a superseded revision")
            if package_hash != head.package_hash:
                raise StaleCommandError("package hash no longer matches current state")
            # A superseded approval can never re-authorize a later revision:
            # any binding already marked superseded stays unusable, and every
            # approval must target the exact current head above.
            for prior_binding in self._approvals.get(case_id, []):
                if prior_binding.superseded and prior_binding.target_revision == revision_id:
                    raise StaleCommandError("approval targets a superseded revision")
            self._check_number_drift(
                approved_ratio, approved_threshold, approved_comparator, approved_inputs,
                fresh_ratio, fresh_threshold, fresh_comparator, fresh_inputs,
            )
            blocking = [
                i for i in self._issues.values()
                if i.case_id == case_id and i.revision_id == revision_id and i.status == "open"
            ]
            if blocking and decision == "approved":
                raise StaleCommandError("blocking review issues remain open")
            if not reason:
                raise ValueError("reason is required")
            prior = [a for a in self._approvals.get(case_id, []) if not a.superseded]
            binding = ApprovalBinding(
                actor=actor,
                role=role,
                case_id=case_id,
                target_revision=revision_id,
                bundle_hash=head.input_bundle_hash,
                package_hash=package_hash,
                decision=decision,
                reason=reason,
                timestamp=_now(),
                approved_ratio=fresh_ratio if fresh_ratio is not None else approved_ratio,
                approved_threshold=fresh_threshold if fresh_threshold is not None else approved_threshold,
                approved_comparator=fresh_comparator if fresh_comparator is not None else approved_comparator,
                approved_inputs=dict(fresh_inputs) if fresh_inputs is not None else dict(approved_inputs or {}),
            )
            if prior:
                binding.superseding_approval_ref = f"{case_id}:{prior[-1].target_revision}:{prior[-1].actor}"
            self._approvals.setdefault(case_id, []).append(binding)
            seq = len(self._events.get(case_id, [])) + 1
            self._events.setdefault(case_id, []).append(
                {"sequence": seq, "name": "APPROVAL_RECORDED", "revision_id": revision_id}
            )
            return binding

    # -- snapshot -----------------------------------------------------------
    def snapshot(self, case_id: str) -> dict:
        with self._lock:
            head = self.current(case_id)
            snap = self._snapshots[case_id][head.revision_id]
            approvals = [a.model_dump(mode="json") for a in self._approvals.get(case_id, [])]
            open_issues = sum(
                1 for i in self._issues.values()
                if i.case_id == case_id and i.revision_id == head.revision_id and i.status == "open"
            )
            events = self._events.get(case_id, [])
            return {
                "case_id": case_id,
                "revision": head.model_dump(mode="json"),
                "run_state": "waiting_review" if open_issues else "completed",
                "per_covenant_results": [
                    {"rule_id": head.rule_id, "threshold": head.threshold, "status": "stale" if open_issues else "current"}
                ],
                "coverage": {"state": "complete_for_declared_scope", "hash": head.coverage_hash},
                "package_state": "ready_for_officer_review" if open_issues else "draft",
                "package_hash": head.package_hash,
                "open_review_issues": open_issues,
                "documents": snap["documents"],
                "approvals": approvals,
                "last_event_sequence": events[-1]["sequence"] if events else 0,
            }


store = RevisionStore()
