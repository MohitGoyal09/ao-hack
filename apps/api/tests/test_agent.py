"""Agent document-ingestion and re-evaluation tools (Gap 4)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.agent import ingest_document_for_case, reevaluate_case
from src.covenant import build_demo_workflow

DATA_ROOT = Path(__file__).resolve().parents[3] / "data" / "raw"
AGREEMENT_PDF = DATA_ROOT / "pdf-fixtures" / "aon-credit-agreement.pdf"
FINANCIALS_HTML = DATA_ROOT / "sec" / "aon" / "2023-form-10k.html"


class AgentDocumentToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = build_demo_workflow()
        cls.case_id = cls.workflow.list_cases()[0]["id"]

    def test_ingest_agreement_returns_real_extraction(self):
        payload = json.loads(
            ingest_document_for_case("any-case", str(AGREEMENT_PDF), "agreement")
        )
        self.assertEqual(payload["document_kind"], "agreement")
        self.assertTrue(payload["document_hash"])
        tiers = payload["rule"]["tiers"]
        self.assertEqual([t["threshold"] for t in tiers], [4.0, 3.75, 3.25])
        self.assertIn("Consolidated Leverage Ratio", payload["rule"]["section_excerpt"])

    def test_ingest_financials_returns_real_facts(self):
        payload = json.loads(
            ingest_document_for_case("any-case", str(FINANCIALS_HTML), "financials")
        )
        keys = {fact["key"] for fact in payload["facts"]}
        self.assertTrue({"funded_debt", "ebitda", "net_income"} <= keys)
        ebitda = next(f for f in payload["facts"] if f["key"] == "ebitda")
        self.assertGreater(ebitda["amount"], 0)

    def test_ingest_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            ingest_document_for_case("any-case", str(AGREEMENT_PDF), "email")

    def test_reevaluate_case_returns_real_run(self):
        raw = reevaluate_case(self.workflow, self.case_id)
        payload = json.loads(raw)
        self.assertIn("status", payload)
        self.assertIn("calculation", payload)


if __name__ == "__main__":
    unittest.main()
