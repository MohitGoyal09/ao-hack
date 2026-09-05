"""Dataset-gate tests (contract Task 0 / gap 8).

Every reviewed label in data/gold/ must carry reviewer identity, review
date, rationale, source spans and review scope, and every source span must
resolve to a real data/raw/ file. No gold label may claim a compliance
verdict: review scope here is extraction-only.
"""

import html
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GOLD = REPO / "data" / "gold"
RAW = REPO / "data" / "raw"

REQUIRED_REVIEW_KEYS = {
    "reviewer",
    "review_date",
    "review_scope",
    "rationale",
}


def normalized_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text)


class DatasetGateTests(unittest.TestCase):
    def test_gold_labels_are_not_empty(self):
        labels = sorted(GOLD.glob("*.json"))
        self.assertGreater(len(labels), 0, "data/gold/ must hold reviewed labels")

    def test_gold_labels_carry_reviewer_metadata(self):
        for path in sorted(GOLD.glob("*.json")):
            with self.subTest(label=path.name):
                label = json.loads(path.read_text())
                self.assertEqual(label.get("status"), "REVIEWED")
                review = label.get("review", {})
                missing = REQUIRED_REVIEW_KEYS - set(review)
                self.assertEqual(missing, set(), f"missing review keys: {missing}")
                self.assertTrue(label.get("source_spans"), "needs source spans")
                for span in label["source_spans"]:
                    self.assertIn("source_path", span)
                    self.assertIn("anchor_text", span)
                    self.assertTrue(span["anchor_text"].strip())

    def test_gold_labels_claim_no_verdict(self):
        for path in sorted(GOLD.glob("*.json")):
            with self.subTest(label=path.name):
                label = json.loads(path.read_text())
                self.assertFalse(
                    label.get("review", {}).get("verdict_claimed", False),
                    "extraction-only labels must not claim a verdict",
                )
                self.assertIn(label["review"]["review_scope"], {"extraction-only"})

    def test_gold_spans_trace_to_raw_sources(self):
        cache: dict = {}
        for path in sorted(GOLD.glob("*.json")):
            with self.subTest(label=path.name):
                label = json.loads(path.read_text())
                for span in label["source_spans"]:
                    source = RAW / span["source_path"].replace("raw/", "", 1)
                    self.assertTrue(
                        source.is_file(), f"source missing: {span['source_path']}"
                    )
                    if str(source) not in cache:
                        cache[str(source)] = normalized_text(source)
                    self.assertIn(
                        span["anchor_text"],
                        cache[str(source)],
                        f"anchor not found in {span['source_path']}",
                    )

    def test_case_readiness_stays_not_ready(self):
        readiness = json.loads(
            (REPO / "data" / "case-readiness.json").read_text()
        )
        for package in readiness["packages"]:
            with self.subTest(package=package["id"]):
                self.assertFalse(package["full_verdict_ready"])


if __name__ == "__main__":
    unittest.main()
