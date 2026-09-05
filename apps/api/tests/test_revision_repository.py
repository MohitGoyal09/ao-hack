"""Revision repository: restart survival, supersede, stale, factory fail-closed."""

from __future__ import annotations

import os
import unittest
import uuid
from unittest.mock import patch

from src.covenant.revision_repository import (
    MemoryRevisionRepository,
    PostgresRevisionRepository,
    is_postgres_configured,
    revision_repository_from_env,
)
from src.covenant.revisions import (
    IdempotencyConflictError,
    StaleCommandError,
)

def _ids(prefix: str) -> tuple[str, str, str]:
    org = str(uuid.uuid4())
    user = str(uuid.uuid4())
    return org, user, f"{prefix}-{uuid.uuid4().hex[:8]}"


def _provision_org_case(cur, org: str, user: str, case_id: str,
                        role: str = "treasury_reviewer") -> None:
    cur.execute(
        "insert into auth.users (id) values (%s) on conflict (id) do nothing",
        (user,),
    )
    cur.execute(
        "insert into public.organizations (id, name, slug, created_by)"
        " values (%s, %s, %s, %s) on conflict (id) do nothing",
        (org, f"org-{org[:8]}", f"org-{org[:8]}", user),
    )
    cur.execute(
        "insert into public.organization_members (organization_id, user_id, role)"
        " values (%s, %s, %s) on conflict do nothing",
        (org, user, role),
    )


class MemoryRepositoryTests(unittest.TestCase):
    def test_new_revision_supersedes_old_approval(self) -> None:
        repo = MemoryRevisionRepository()
        org, user, case = _ids("case")
        repo.seed_member(org, user, "officer")
        repo.ensure_case(case, org, user, "2026-06-30", "rule-1", "4.00",
                         ["doc-1"], ["f1"])
        head = repo.current(case)
        repo.resolve_issue(f"{case}-evidence-1", org, user, "treasury_reviewer",
                           head.revision_id, head.input_bundle_hash,
                           "accept_evidence", "verified", ["doc:doc-1"], "k-1")
        snap = repo.snapshot(case)
        repo.approve(case, org, user, "officer", head.revision_id,
                     snap["package_hash"], "approved", "ok",
                     fresh_ratio="4.17", fresh_threshold=head.threshold,
                     fresh_comparator="<=",
                     fresh_inputs={"f1": "1.00"})
        repo.create_revision(case, org, user, head.revision_id, "amendment",
                             ["doc-2"], [], None)
        approvals = repo.snapshot(case)["approvals"]
        old = [a for a in approvals if a["target_revision"] == head.revision_id]
        self.assertTrue(old and all(a["superseded"] for a in old))

    def test_stale_revision_command_returns_409(self) -> None:
        repo = MemoryRevisionRepository()
        org, user, case = _ids("case")
        repo.ensure_case(case, org, user, "2026-06-30", "rule-1", "4.00",
                         ["doc-1"], ["f1"])
        head = repo.current(case)
        repo.create_revision(case, org, user, head.revision_id, "amendment",
                             ["doc-2"], [], None)
        with self.assertRaises(StaleCommandError):
            repo.create_revision(case, org, user, head.revision_id, "amendment",
                                 ["doc-3"], [], None)

    def test_idempotency_same_key_same_request_replays(self) -> None:
        repo = MemoryRevisionRepository()
        org, user, case = _ids("case")
        repo.ensure_case(case, org, user, "2026-06-30", "rule-1", "4.00",
                         ["doc-1"], ["f1"])
        head = repo.current(case)
        first = repo.resolve_issue(
            f"{case}-evidence-1", org, user, "treasury_reviewer",
            head.revision_id, head.input_bundle_hash, "accept_evidence",
            "verified", [], "dup-key")
        replay = repo.resolve_issue(
            f"{case}-evidence-1", org, user, "treasury_reviewer",
            head.revision_id, head.input_bundle_hash, "accept_evidence",
            "verified", [], "dup-key")
        self.assertEqual(first, replay)
        with self.assertRaises(IdempotencyConflictError):
            repo.resolve_issue(
                f"{case}-evidence-1", org, user, "treasury_reviewer",
                head.revision_id, head.input_bundle_hash, "accept_evidence",
                "changed", [], "dup-key")

    def test_money_serialized_as_exact_strings(self) -> None:
        repo = MemoryRevisionRepository()
        org, user, case = _ids("case")
        rev = repo.ensure_case(case, org, user, "2026-06-30", "rule-1", 4,
                               ["doc-1"], ["f1"])
        self.assertEqual(rev.threshold, "4.00")
        self.assertIsInstance(rev.threshold, str)


class RepositoryFactoryTests(unittest.TestCase):
    def test_offline_mode_uses_memory_repository(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(is_postgres_configured())
            repo = revision_repository_from_env()
        self.assertIsInstance(repo, MemoryRevisionRepository)

    def test_configured_postgres_failure_raises_instead_of_fallback(self) -> None:
        from src.platform.jobqueue import DurabilityConfigurationError
        with patch.dict("os.environ",
                        {"DATABASE_URL": "postgresql://127.0.0.1:1/nope"},
                        clear=True):
            self.assertTrue(is_postgres_configured())
            with self.assertRaises(DurabilityConfigurationError):
                revision_repository_from_env()


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is not configured")
class PostgresRevisionRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dsn = os.environ["TEST_DATABASE_URL"]

    def _repo(self) -> PostgresRevisionRepository:
        repo = PostgresRevisionRepository(self.dsn)
        repo.verify()
        return repo

    def _setup_case(self, repo, role="treasury_reviewer"):
        import psycopg
        org, user, case = _ids("pgcase")
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                _provision_org_case(cur, org, user, case, role)
                if role != "officer":
                    officer = str(uuid.uuid4())
                    cur.execute(
                        "insert into auth.users (id) values (%s)"
                        " on conflict (id) do nothing",
                        (officer,),
                    )
                    cur.execute(
                        "insert into public.organization_members"
                        " (organization_id, user_id, role) values (%s, %s, 'officer')",
                        (org, officer),
                    )
                else:
                    officer = user
        head = repo.ensure_case(case, org, user, "2026-06-30", "rule-pg",
                                "4.00", ["doc-1"], ["f1"])
        return org, user, officer, case, head

    def test_revision_history_survives_reconstruction(self) -> None:
        repo = self._repo()
        org, user, officer, case, head = self._setup_case(repo)
        repo.create_revision(case, org, user, head.revision_id, "amendment",
                             ["doc-2"], [], "4.25")
        rebuilt = self._repo()
        current = rebuilt.current(case)
        self.assertNotEqual(current.revision_id, head.revision_id)
        self.assertEqual(current.threshold, "4.25")
        fetched = rebuilt.get(case, head.revision_id)
        self.assertEqual(fetched.status, "superseded")
        snap = rebuilt.snapshot(case)
        self.assertEqual(snap["revision"]["revision_id"], current.revision_id)
        events = rebuilt.list_events(case)
        self.assertGreaterEqual(len(events), 3)

    def test_review_resolution_survives_reconstruction(self) -> None:
        repo = self._repo()
        org, user, officer, case, head = self._setup_case(repo)
        repo.resolve_issue(f"{case}-evidence-1", org, user, "treasury_reviewer",
                           head.revision_id, head.input_bundle_hash,
                           "accept_evidence", "verified", ["doc:doc-1"], "rk-1")
        rebuilt = self._repo()
        snap = rebuilt.snapshot(case)
        self.assertEqual(snap["open_review_issues"], 0)

    def test_officer_approval_survives_reconstruction(self) -> None:
        repo = self._repo()
        org, user, officer, case, head = self._setup_case(repo, role="officer")
        repo.resolve_issue(f"{case}-evidence-1", org, officer, "officer",
                           head.revision_id, head.input_bundle_hash,
                           "accept_evidence", "verified", ["doc:doc-1"], "rk-2")
        snap = repo.snapshot(case)
        repo.approve(case, org, officer, "officer", head.revision_id,
                     snap["package_hash"], "approved", "reviewed",
                     fresh_ratio="4.17", fresh_threshold=head.threshold,
                     fresh_comparator="<=",
                     fresh_inputs={"f1": "1.00"})
        rebuilt = self._repo()
        approvals = rebuilt.snapshot(case)["approvals"]
        self.assertTrue(any(a["target_revision"] == head.revision_id
                            for a in approvals))

    def test_idempotency_survives_reconstruction(self) -> None:
        repo = self._repo()
        org, user, officer, case, head = self._setup_case(repo)
        first = repo.resolve_issue(
            f"{case}-evidence-1", org, user, "treasury_reviewer",
            head.revision_id, head.input_bundle_hash, "accept_evidence",
            "verified", ["doc:doc-1"], "idem-1")
        rebuilt = self._repo()
        replay = rebuilt.resolve_issue(
            f"{case}-evidence-1", org, user, "treasury_reviewer",
            head.revision_id, head.input_bundle_hash, "accept_evidence",
            "verified", ["doc:doc-1"], "idem-1")
        self.assertEqual(first, replay)
        with self.assertRaises(IdempotencyConflictError):
            rebuilt.resolve_issue(
                f"{case}-evidence-1", org, user, "treasury_reviewer",
                head.revision_id, head.input_bundle_hash, "accept_evidence",
                "changed mind", ["doc:doc-1"], "idem-1")

    def test_new_revision_supersedes_old_approval(self) -> None:
        repo = self._repo()
        org, user, officer, case, head = self._setup_case(repo, role="officer")
        repo.resolve_issue(f"{case}-evidence-1", org, officer, "officer",
                           head.revision_id, head.input_bundle_hash,
                           "accept_evidence", "verified", ["doc:doc-1"], "rk-3")
        snap = repo.snapshot(case)
        repo.approve(case, org, officer, "officer", head.revision_id,
                     snap["package_hash"], "approved", "reviewed",
                     fresh_ratio="4.17", fresh_threshold=head.threshold,
                     fresh_comparator="<=",
                     fresh_inputs={"f1": "1.00"})
        repo.create_revision(case, org, user, head.revision_id, "amendment",
                             ["doc-2"], [], None)
        rebuilt = self._repo()
        approvals = rebuilt.snapshot(case)["approvals"]
        old = [a for a in approvals if a["target_revision"] == head.revision_id]
        self.assertTrue(old and all(a["superseded"] for a in old))
        with self.assertRaises(StaleCommandError):
            rebuilt.approve(case, org, officer, "officer", head.revision_id,
                            snap["package_hash"], "approved", "reused",
                            fresh_ratio="4.17", fresh_threshold=head.threshold,
                            fresh_comparator="<=",
                            fresh_inputs={"f1": "1.00"})

    def test_stale_revision_and_stale_hash_return_409(self) -> None:
        repo = self._repo()
        org, user, officer, case, head = self._setup_case(repo)
        repo.create_revision(case, org, user, head.revision_id, "amendment",
                             ["doc-2"], [], None)
        with self.assertRaises(StaleCommandError):
            repo.create_revision(case, org, user, head.revision_id, "amendment",
                                 ["doc-3"], [], None)
        rebuilt = self._repo()
        current = rebuilt.current(case)
        with self.assertRaises(StaleCommandError):
            rebuilt.resolve_issue(
                f"{case}-evidence-1", org, user, "treasury_reviewer",
                head.revision_id, head.input_bundle_hash, "accept_evidence",
                "late", [], "stale-1")


if __name__ == "__main__":
    unittest.main()
