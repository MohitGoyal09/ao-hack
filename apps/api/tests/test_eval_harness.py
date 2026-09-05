"""Evaluation-harness gate (scripts/eval.py) run in-process.

Asserts the invariants judges are shown in docs/evaluation.md: every golden
calculation matches, no blocked-condition run ever yields DRAFT_COMPLIANT,
every supported gold label passes, and every cited span resolves in its
source. The slow upload->pipeline section (re-parses three PDFs) is exercised
by the script itself, not here. Skips when the data/raw fixtures are absent.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
HARNESS = API_ROOT / "scripts" / "eval.py"
AON_PDF = API_ROOT.parents[1] / "data" / "raw" / "pdf-fixtures" / "aon-credit-agreement.pdf"


def _load_harness():
    spec = importlib.util.spec_from_file_location("eval_harness", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(AON_PDF.is_file(), "data/raw fixtures are not checked out")
class EvalHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = _load_harness()

    def test_golden_calculations_all_match(self) -> None:
        golden = self.harness.golden_calculations()
        mismatches = [r for r in golden["rows"] if not r["match"]]
        self.assertEqual(mismatches, [], f"golden mismatches: {mismatches}")
        self.assertEqual(golden["match"], golden["total"])
        self.assertGreaterEqual(golden["total"], 7)

    def test_no_false_passes(self) -> None:
        report = self.harness.false_passes()
        self.assertEqual(report["false_passes"], 0, report["rows"])
        self.assertEqual(report["compliant_with_blocker"], 0)
        self.assertGreaterEqual(report["blocked_condition_runs"], 8)

    def test_supported_gold_labels_pass_and_unsupported_are_counted(self) -> None:
        report = self.harness.extraction_vs_gold()
        failed = [r["label"] for r in report["rows"] if r["result"] == "FAIL"]
        self.assertEqual(failed, [])
        self.assertEqual(report["PASS"], report["supported"])
        self.assertEqual(report["PASS"] + report["UNSUPPORTED"] + report["SKIPPED"], report["total"])
        self.assertEqual(report["total"], 10)

    def test_every_cited_span_resolves(self) -> None:
        report = self.harness.span_validity()
        invalid = [r for r in report["rows"] if r["valid"] is False]
        self.assertEqual(invalid, [])
        self.assertEqual(report["valid"], report["total"])
        self.assertEqual(report["gold_anchors_valid"], report["gold_anchors_total"])

    def test_report_is_json_serialisable_and_ok(self) -> None:
        import json

        report = self.harness.evaluate(uploads=False)
        self.assertTrue(report["ok"])
        json.dumps(report, sort_keys=True)


if __name__ == "__main__":
    unittest.main()
