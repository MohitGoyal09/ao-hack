"""CasePipeline tests: memory happy/unsupported paths + Postgres durability.

Memory tests stay hermetic: no repo data files are read. The unsupported
path runs end-to-end on CSV bytes (real extraction fails honestly); the
supported path monkeypatches the ingestion extractors with canned results.
"""

from __future__ import annotations

import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from src.covenant import ingestion
from src.covenant.documents import UnknownDocumentError
from src.covenant.ingestion import ExtractedAonRule, ExtractedFinancialFact
from src.covenant.pipeline import (
    CasePipeline,
    PermanentRunError,
    TransientRunError,
)
from src.platform.storage import MemoryStorageAdapter

CSV_BYTES = b"period,amount\n2023-01,100.00\n2023-02,200.00\n"

FAKE_RULE = ExtractedAonRule(
    name="Maximum Consolidated Leverage Ratio",
    formula_label="Consolidated Funded Debt / Consolidated Adjusted EBITDA",
    comparator="<=",
    tiers=(
        ingestion.LeverageTier("step-i", 4.0),
        ingestion.LeverageTier("step-ii", 3.75),
        ingestion.LeverageTier("step-iii", 3.25),
    ),
    section="6.14(b)",
    section_page=10,
    section_excerpt="section excerpt",
    definition_page=5,
    definition_excerpt="definition excerpt",
    document_id="doc-1",
    document_title="Credit Agreement",
    effective_date="2024-02-16",
    document_hash="ab" * 32,
)

FAKE_FACTS = (
    ExtractedFinancialFact("funded_debt", "Total debt", 8000.0, "Note 15"),
    ExtractedFinancialFact("net_income", "Net income", 1000.0, "Income"),
    ExtractedFinancialFact("income_tax", "Income tax", 500.0, "Income"),
    ExtractedFinancialFact("interest_expense", "Interest", 400.0, "Income"),
    ExtractedFinancialFact("depreciation", "Depreciation", 200.0, "Income"),
    ExtractedFinancialFact("amortization", "Amortization", 100.0, "Income"),
)


def _upload(pipeline: CasePipeline, **overrides):
    kwargs = {
        "organization_id": "org-1",
        "user_id": "user-1",
        "case_id": "case-1",
        "filename": "statement.csv",
        "content_type": "text/csv",
        "data": CSV_BYTES,
        "document_role": "financial_statement",
        "title": "Q1 statement",
    }
    kwargs.update(overrides)
    return pipeline.documents.upload(**kwargs)


def _job(case_id: str, revision_id: str, document_id: str, version: int = 1):
    return SimpleNamespace(
        id=f"job-{uuid.uuid4().hex[:12]}",
        case_id=case_id,
        revision_id=revision_id,
        payload={"document_id": document_id, "version": version},
    )


class MemoryUnsupportedPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = CasePipeline(None, MemoryStorageAdapter())
        self.version = _upload(self.pipeline)
        self.job = _job("case-1", "rev-1", self.version.document_id)

    def test_unsupported_returns_waiting_review_with_manifest(self) -> None:
        calls: list[int] = []
        self.pipeline.begin(self.job)
        self.assertEqual(
            self.pipeline.run_state("case-1", "rev-1"), "running"
        )
        result = self.pipeline.run(self.job, on_progress=lambda: calls.append(1))
        self.assertEqual(result["status"], "waiting_review")
        self.assertEqual(result["revision_id"], "rev-1")
        self.assertIsNone(result["calculation"])
        self.assertIsNone(result["error"])
        self.assertEqual(len(result["artifacts"]), 1)
        self.assertEqual(
            result["artifacts"][0]["artifact_type"], "evidence_manifest"
        )
        # Manifest records extraction state + hashes, never invented figures.
        artifacts = self.pipeline.artifacts_for("case-1", "rev-1")
        self.assertEqual(len(artifacts), 1)
        manifest = artifacts[0]["payload"]
        self.assertEqual(manifest["extraction_state"], "unsupported")
        self.assertEqual(manifest["document_sha256"], self.version.sha256)
        self.assertNotIn("ratio", manifest)
        self.assertEqual(
            self.pipeline.run_state("case-1", "rev-1"), "waiting_review"
        )
        events = self.pipeline._events[("case-1", "rev-1")]  # noqa: SLF001
        names = [e["name"] for e in events]
        self.assertIn("RUN_STARTED", names)
        self.assertIn("REVIEW_REQUIRED", names)
        self.assertIn("RUN_COMPLETED", names)

    def test_idempotent_rerun_reuses_manifest(self) -> None:
        self.pipeline.begin(self.job)
        first = self.pipeline.run(self.job, on_progress=lambda: None)
        second = self.pipeline.run(self.job, on_progress=lambda: None)
        self.assertEqual(
            first["artifacts"][0]["content_hash"],
            second["artifacts"][0]["content_hash"],
        )
        rows = self.pipeline._artifacts[("case-1", "rev-1")]  # noqa: SLF001
        current = [r for r in rows if r["state"] == "current"]
        self.assertEqual(len(current), 1)

    def test_unknown_document_raises_permanent(self) -> None:
        job = _job("case-1", "rev-1", str(uuid.uuid4()))
        with self.assertRaises(PermanentRunError):
            self.pipeline.run(job, on_progress=lambda: None)
        self.assertTrue(issubclass(PermanentRunError, Exception))
        self.assertNotIsInstance(PermanentRunError("x"), TransientRunError)

    def test_missing_blob_raises_transient(self) -> None:
        storage = self.pipeline._storage  # noqa: SLF001
        storage._blobs.clear()  # noqa: SLF001
        with self.assertRaises(TransientRunError):
            self.pipeline.run(self.job, on_progress=lambda: None)

    def test_on_progress_called_between_stages(self) -> None:
        calls: list[int] = []
        self.pipeline.begin(self.job)
        self.pipeline.run(self.job, on_progress=lambda: calls.append(1))
        self.assertGreaterEqual(len(calls), 3)


class MemorySupportedPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = CasePipeline(None, MemoryStorageAdapter())
        self.version = _upload(self.pipeline)
        self.job = _job("case-1", "rev-1", self.version.document_id)

    def _run_supported(self, job=None):
        patches = (
            patch(
                "src.covenant.ingestion.extract_aon_rule", return_value=FAKE_RULE
            ),
            patch(
                "src.covenant.ingestion.extract_aon_financials",
                return_value=FAKE_FACTS,
            ),
        )
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        target = job or self.job
        self.pipeline.begin(target)
        return self.pipeline.run(target, on_progress=lambda: None)

    def test_supported_persists_rules_facts_and_package(self) -> None:
        result = self._run_supported()
        self.assertEqual(result["status"], "completed")
        # 8000 / (1000+500+400+200+100=2200) = 3.636.. -> "3.64".
        self.assertEqual(
            result["calculation"],
            {"ratio": "3.64", "threshold": "4.00", "comparator": "<="},
        )
        artifacts = self.pipeline.artifacts_for("case-1", "rev-1")
        types = sorted(a["artifact_type"] for a in artifacts)
        self.assertEqual(
            types,
            ["audit_trace", "calculation", "coverage", "draft_package",
             "evidence_manifest"],
        )
        rules = self.pipeline._rules  # noqa: SLF001
        rule = rules[("case-1", "rev-1", "aon-max-consolidated-leverage")]
        self.assertEqual(rule["covenant_type"], "max_leverage")
        self.assertEqual(rule["support_state"], "supported")
        self.assertEqual(rule["threshold"], "4.00")
        self.assertEqual(len(rule["structured_rule"]["tiers"]), 3)
        facts = self.pipeline._facts  # noqa: SLF001
        debt = facts[("case-1", "rev-1", "funded_debt")]
        self.assertEqual(debt["amount"], "8000.00")
        self.assertEqual(debt["currency"], "USD")
        self.assertEqual(debt["evidence_state"], "accepted")
        self.assertEqual(
            self.pipeline.run_state("case-1", "rev-1"), "completed"
        )

    def test_supported_rerun_is_idempotent(self) -> None:
        first = self._run_supported()
        second = self._run_supported()
        self.assertEqual(
            [a["content_hash"] for a in first["artifacts"]],
            [a["content_hash"] for a in second["artifacts"]],
        )
        rows = self.pipeline._artifacts[("case-1", "rev-1")]  # noqa: SLF001
        self.assertEqual(len(rows), 5)


STATEMENT_BYTES = b"<html>uploaded 10-K stand-in</html>"


def _financials_from(match) -> "callable":
    """Fake extractor: succeeds only for the path *match* accepts."""

    def extractor(path=None):
        if path is not None and match(path):
            return FAKE_FACTS
        raise ValueError("not a 10-K")

    return extractor


class MemoryFallbackTests(unittest.TestCase):
    """Rule from the upload, financials from case evidence or the labelled fixture."""

    def setUp(self) -> None:
        self.pipeline = CasePipeline(None, MemoryStorageAdapter())
        self.version = _upload(
            self.pipeline, document_role="credit_agreement", filename="agreement.pdf",
            content_type="application/pdf",
        )
        self.job = _job("case-1", "rev-1", self.version.document_id)

    def _run(self, financials):
        with patch("src.covenant.ingestion.extract_aon_rule", return_value=FAKE_RULE), \
             patch("src.covenant.ingestion.extract_aon_financials", side_effect=financials):
            self.pipeline.begin(self.job)
            return self.pipeline.run(self.job, on_progress=lambda: None)

    def _manifest(self):
        return next(a for a in self.pipeline.artifacts_for("case-1", "rev-1")
                    if a["artifact_type"] == "evidence_manifest")["payload"]

    def test_missing_case_financials_never_use_bundled_fixture(self) -> None:
        result = self._run(_financials_from(lambda p: p.name == "2023-form-10k.html"))
        self.assertEqual(result["status"], "waiting_review")
        sources = self._manifest()["sources"]
        self.assertEqual(sources["rule"]["kind"], "upload")
        self.assertEqual(sources["facts"]["kind"], "none")
        self.assertFalse(any(a["artifact_type"] == "calculation"
                             for a in self.pipeline.artifacts_for("case-1", "rev-1")))

    def test_case_financial_statement_beats_the_fixture(self) -> None:
        statement = _upload(
            self.pipeline, data=STATEMENT_BYTES, filename="10k.html",
            content_type="text/html", document_role="financial_statement",
        )
        result = self._run(_financials_from(lambda p: p.read_bytes() == STATEMENT_BYTES))
        self.assertEqual(result["status"], "completed")
        facts_source = self._manifest()["sources"]["facts"]
        self.assertEqual(facts_source["kind"], "case_document")
        self.assertEqual(facts_source["document_id"], statement.document_id)
        self.assertEqual(facts_source["sha256"], statement.sha256)

    def test_upload_without_rule_never_reads_fixtures(self) -> None:
        with patch("src.covenant.ingestion.extract_aon_rule", side_effect=ValueError("no")), \
             patch("src.covenant.ingestion.extract_aon_financials") as financials:
            self.pipeline.begin(self.job)
            result = self.pipeline.run(self.job, on_progress=lambda: None)
        self.assertEqual(result["status"], "waiting_review")
        financials.assert_not_called()
        self.assertEqual(self._manifest()["sources"]["facts"]["kind"], "skipped")

    def test_bound_memory_repository_snapshot_sees_worker_output(self) -> None:
        from src.covenant.revision_repository import MemoryRevisionRepository

        repo = MemoryRevisionRepository()
        repo.ensure_case("case-1", "org-1", "user-1", "2024-03-31",
                         "aon-max-consolidated-leverage", "4.00", ["doc-0"], [])
        pipeline = CasePipeline(None, MemoryStorageAdapter(), revision_repository=repo)
        version = _upload(pipeline, document_role="credit_agreement")
        job = _job("case-1", "rev-1", version.document_id)
        with patch("src.covenant.ingestion.extract_aon_rule", return_value=FAKE_RULE), \
             patch("src.covenant.ingestion.extract_aon_financials", return_value=FAKE_FACTS):
            pipeline.begin(job)
            self.assertEqual(repo.snapshot("case-1")["run_state"], "running")
            pipeline.run(job, on_progress=lambda: None)
        snap = repo.snapshot("case-1")
        self.assertEqual(snap["run_state"], "completed")
        self.assertEqual(snap["artifacts"]["calculation"]["ratio"], "3.64")
        self.assertEqual(snap["artifacts"]["calculation"]["threshold"], "4.00")
        self.assertEqual(len(snap["artifacts"]["calculation"]["content_hash"]), 64)
        self.assertEqual(snap["covenant_rules"][0]["external_rule_id"],
                         "aon-max-consolidated-leverage")
        self.assertEqual(snap["covenant_rules"][0]["threshold"], "4.00")
        self.assertEqual({f["fact_key"] for f in snap["financial_facts"]},
                         {f.key for f in FAKE_FACTS})
        self.assertEqual(snap["review_issues"][0]["issue_id"], "case-1-evidence-1")
        self.assertEqual(snap["review_issues"][0]["status"], "open")
        names = [e["name"] for e in repo.list_events("case-1")]
        expected_progress = [
            "RUN_STARTED", "DOCUMENT_READ", "AGREEMENT_RESOLVED",
            "DEFINITIONS_COMPILED", "EVIDENCE_MAPPED",
            "CALCULATION_STARTED", "CALCULATION_COMPLETED", "RUN_COMPLETED",
        ]
        positions = [names.index(event) for event in expected_progress]
        self.assertEqual(positions, sorted(positions))
        pipeline.set_run_state(job, "failed")
        self.assertEqual(repo.snapshot("case-1")["run_state"], "failed")


def _provision_org_case(cur, org: str, user: str, case_id: str) -> None:
    cur.execute(
        "insert into auth.users (id) values (%s) on conflict (id) do nothing",
        (user,),
    )
    cur.execute(
        "insert into public.organizations (id, name, slug, created_by)"
        " values (%s, %s, %s, %s) on conflict (id) do nothing",
        (org, f"org-{org[:8]}", f"pipe-{org[:8]}", user),
    )
    cur.execute(
        "insert into public.organization_members (organization_id, user_id, role)"
        " values (%s, %s, 'treasury_reviewer') on conflict do nothing",
        (org, user),
    )


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is not configured")
class PostgresPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        import psycopg

        from src.covenant.documents import DocumentService
        from src.covenant.revision_repository import PostgresRevisionRepository

        self.dsn = os.environ["TEST_DATABASE_URL"]
        self.storage = MemoryStorageAdapter()
        self.org = str(uuid.uuid4())
        self.user = str(uuid.uuid4())
        self.case_id = f"pipe-{uuid.uuid4().hex[:8]}"
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                _provision_org_case(cur, self.org, self.user, self.case_id)
        repo = PostgresRevisionRepository(self.dsn)
        rev = repo.ensure_case(
            self.case_id, self.org, self.user, "2024-03-31",
            "aon-max-consolidated-leverage", "4.00", [], [],
        )
        self.revision_id = rev.revision_id
        svc = DocumentService(self.dsn, self.storage)
        self.version = svc.upload(
            organization_id=self.org,
            user_id=self.user,
            case_id=self.case_id,
            filename="statement.csv",
            content_type="text/csv",
            data=CSV_BYTES,
            document_role="financial_statement",
            title="Q1 statement",
        )

    def _job(self):
        return SimpleNamespace(
            id=f"job-{uuid.uuid4().hex[:12]}",
            case_id=self.case_id,
            revision_id=self.revision_id,
            payload={"document_id": self.version.document_id, "version": 1},
        )

    def test_artifacts_and_run_state_survive_reconstruction(self) -> None:
        calls: list[int] = []
        pipeline = CasePipeline(self.dsn, self.storage)
        job = self._job()
        pipeline.begin(job)
        self.assertEqual(
            pipeline.run_state(self.case_id, self.revision_id), "running"
        )
        result = pipeline.run(job, on_progress=lambda: calls.append(1))
        self.assertEqual(result["status"], "waiting_review")
        self.assertGreaterEqual(len(calls), 3)

        rebuilt = CasePipeline(self.dsn, self.storage)
        self.assertEqual(
            rebuilt.run_state(self.case_id, self.revision_id), "waiting_review"
        )
        artifacts = rebuilt.artifacts_for(self.case_id, self.revision_id)
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["artifact_type"], "evidence_manifest")
        self.assertEqual(
            artifacts[0]["content_hash"], result["artifacts"][0]["content_hash"]
        )

    def test_unknown_document_raises_permanent_postgres(self) -> None:
        pipeline = CasePipeline(self.dsn, self.storage)
        job = SimpleNamespace(
            id=f"job-{uuid.uuid4().hex[:12]}",
            case_id=self.case_id,
            revision_id=self.revision_id,
            payload={"document_id": str(uuid.uuid4()), "version": 1},
        )
        with self.assertRaises((PermanentRunError, UnknownDocumentError)):
            pipeline.run(job, on_progress=lambda: None)


if __name__ == "__main__":
    unittest.main()
