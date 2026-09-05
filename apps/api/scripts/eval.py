"""Deterministic, offline evaluation harness for Covenant Certificate.

Run from ``apps/api``::

    uv run python scripts/eval.py          # Markdown tables
    uv run python scripts/eval.py --json   # machine-readable, byte-stable

Everything is stdlib + the existing ``src.covenant`` modules: no model, no
network, no database. Every count is printed with its denominator. Sections:

1. extraction_vs_gold     each reviewed label in data/gold/ is PASS / FAIL /
                          UNSUPPORTED (the v1 parser reads one shape: the Aon
                          Section 6.14(b) PDF layout; other labels are counted,
                          not hidden).
2. span_validity          every cited locator + excerpt the product shows for
                          the real-source case resolves in the source text;
                          gold anchors resolve in data/raw/; synthetic cases
                          have no source document and are listed as such.
3. golden_calculations    curated cases -> expected (status, ratio, threshold).
4. false_passes           DRAFT_COMPLIANT while a blocking condition exists.
                          Must be 0; the observed 0/N is a result, not a proof.
5. unsupported_detection  non-Aon documents pushed through the real upload ->
                          CasePipeline path never yield a verdict.

Exit status is 1 when any golden calculation mismatches or a false pass exists.
Runtime is dominated by pdfplumber (three ~100-page PDFs, roughly a minute).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from src.covenant import ingestion  # noqa: E402
from src.covenant.catalog import build_demo_catalog  # noqa: E402
from src.covenant.documents import classify_upload  # noqa: E402
from src.covenant.domain import DraftStatus, RunRequest, money_str  # noqa: E402
from src.covenant.pipeline import CasePipeline  # noqa: E402
from src.covenant.policy import period_end  # noqa: E402
from src.covenant.repository import InMemoryRepository  # noqa: E402
from src.covenant.workflow import CovenantWorkflow  # noqa: E402
from src.platform.storage import MemoryStorageAdapter  # noqa: E402

REPO = API_ROOT.parents[1]
GOLD = REPO / "data" / "gold"
DERIVED = REPO / "data" / "derived"
RAW = ingestion.data_root()
AON_PDF = RAW / "pdf-fixtures" / "aon-credit-agreement.pdf"
AON_10K = RAW / "sec" / "aon" / "2023-form-10k.html"
SYNTHETIC_CASES = ("aurora-net-leverage", "beacon-gross-leverage", "beacon-amendment",
                   "meridian-evidence-gap")
UNSUPPORTED_REASON = ("single-shape parser: v1 extracts only the Aon Section 6.14(b) "
                      "PDF layout; no extractor exists for this document")

APPROVE = dict(reviewer_decision="approve_addback", reviewer_name="A. Treasurer",
               reviewer_rationale="Management schedule reconciled to the ledger.")
REJECT = dict(reviewer_decision="reject_addback", reviewer_name="A. Treasurer",
              reviewer_rationale="Requested support was not delivered.")


def _labels() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(GOLD.glob("*.json"))]


def _raw(source_path: str) -> Path:
    return RAW / source_path.replace("raw/", "", 1)


def _source_text(path: Path) -> str:
    return ingestion._html_text(path)  # noqa: SLF001  (html unescape + tag strip + collapse)


def _run(case_id: str, request: dict | None = None, catalog: dict | None = None):
    workflow = CovenantWorkflow(InMemoryRepository(catalog or build_demo_catalog()))
    return workflow.run(case_id, RunRequest(**(request or {})))


def _blocking_codes(result) -> list[str]:
    return sorted({i.code for i in result.review_issues if i.severity == "blocking"})


# --------------------------------------------------------------------------
# 1. extraction vs gold
# --------------------------------------------------------------------------

def _anchor_on_page(label: dict, page: int) -> bool:
    pages = ingestion._pdf_page_texts(AON_PDF)  # noqa: SLF001
    anchor = ingestion._collapse(label["source_spans"][0]["anchor_text"])  # noqa: SLF001
    return anchor in pages[page - 1]


def _check_threshold(label: dict) -> dict:
    rule = ingestion.extract_aon_rule(AON_PDF)
    anchor = label["source_spans"][0]["anchor_text"]
    expected = re.findall(r"not more than (\d\.\d{2}):1\.00", anchor)
    got = [money_str(t.threshold) for t in rule.tiers]
    derived = json.loads((DERIVED / "aon-2024-leverage-thresholds.json").read_text())
    derived_steps = [s["max_leverage"].split(":")[0] for s in derived["steps"]]
    checks = {
        "thresholds_in_order": got == expected,
        "derived_table_agrees": derived_steps == expected,
        "anchor_on_cited_page": _anchor_on_page(label, rule.section_page),
        "section": rule.section == "6.14(b)",
    }
    return {"expected": expected, "got": got, "cited_page": rule.section_page, "checks": checks}


def _check_definition(label: dict) -> dict:
    rule = ingestion.extract_aon_rule(AON_PDF)
    derived = json.loads((DERIVED / "aon-2024-leverage-definition.json").read_text())
    excerpt = ingestion._collapse(rule.definition_excerpt)  # noqa: SLF001
    anchor = ingestion._collapse(label["source_spans"][0]["anchor_text"])  # noqa: SLF001
    checks = {
        "numerator_in_formula": "Consolidated Funded Debt" in rule.formula_label
        and derived["numerator"].startswith("Consolidated Funded Debt"),
        "denominator_in_formula": "Consolidated Adjusted EBITDA" in rule.formula_label
        and derived["denominator"].startswith("Consolidated Adjusted EBITDA"),
        "anchor_in_extracted_excerpt": anchor in excerpt,
        "anchor_on_cited_page": _anchor_on_page(label, rule.definition_page),
        "comparator": rule.comparator == "<=",
    }
    return {"expected": {"numerator": derived["numerator"], "denominator": derived["denominator"]},
            "got": rule.formula_label, "cited_page": rule.definition_page, "checks": checks}


def _check_period_mismatch(label: dict) -> dict:
    facts = ingestion.extract_aon_financials(AON_10K)
    text = _source_text(AON_10K)
    result = _run("aon-term-loan-leverage")
    fact_period = period_end(ingestion.AON_FINANCIAL_PERIOD)
    checks = {
        "financials_extracted": len(facts) == 7 and all(f.amount > 0 for f in facts),
        "fact_period_is_fy2023": fact_period == "2023-12-31",
        "filing_anchor_in_10k": label["source_spans"][0]["anchor_text"] in text,
        "period_precedes_first_test": fact_period < ingestion.AON_TEST_DATE,
        "run_refuses_verdict": result.status == DraftStatus.REVIEW
        and _blocking_codes(result) == ["FINANCIAL_PERIOD_MISMATCH"],
        "refusal_names_both_periods": "2023-12-31" in result.status_reason
        and ingestion.AON_TEST_DATE in result.status_reason,
    }
    return {"expected": {"fact_period_end": "2023-12-31", "status": "NEEDS_REVIEW",
                         "blocking": ["FINANCIAL_PERIOD_MISMATCH"]},
            "got": {"fact_period_end": fact_period, "status": result.status.value,
                    "blocking": _blocking_codes(result)},
            "checks": checks}


CHECKERS = {
    "aon-2024-lev-threshold-001": _check_threshold,
    "aon-2024-lev-definition-001": _check_definition,
    "aon-2024-period-mismatch-001": _check_period_mismatch,
}


def extraction_vs_gold() -> dict:
    rows = []
    for label in _labels():
        row = {"label": label["label_id"], "package": label["package_id"]}
        missing = [s["source_path"] for s in label["source_spans"] if not _raw(s["source_path"]).is_file()]
        if missing:
            row.update(result="SKIPPED", reason=f"source missing: {missing}")
        elif label["label_id"] in CHECKERS:
            detail = CHECKERS[label["label_id"]](label)
            row.update(result="PASS" if all(detail["checks"].values()) else "FAIL", **detail)
        else:
            row.update(result="UNSUPPORTED", reason=UNSUPPORTED_REASON)
            if label["label_id"] == "aon-2024-interest-coverage-001":
                # Not extracted; the Aon case declares it as an excluded obligation.
                excluded = _run("aon-term-loan-leverage").coverage.excluded
                row["detected_as_unsupported_obligation"] = any(
                    "interest coverage" in e.lower() for e in excluded)
        rows.append(row)
    counts = {k: sum(r["result"] == k for r in rows) for k in ("PASS", "FAIL", "UNSUPPORTED", "SKIPPED")}
    return {"rows": rows, **counts, "total": len(rows),
            "supported": counts["PASS"] + counts["FAIL"]}


# --------------------------------------------------------------------------
# 2. citation / span validity
# --------------------------------------------------------------------------

def span_validity() -> dict:
    catalog = build_demo_catalog()
    aon = catalog["aon-term-loan-leverage"]
    pages = ingestion._pdf_page_texts(AON_PDF)  # noqa: SLF001
    tenk = _source_text(AON_10K)
    rows = []
    for citation in aon.rule.citations:
        page = int(re.search(r"PDF p\. (\d+)", citation.locator).group(1))
        excerpt = ingestion._collapse(citation.excerpt.removesuffix("…"))  # noqa: SLF001
        rows.append({"case": aon.id, "kind": "clause", "locator": citation.locator,
                     "valid": 0 < page <= len(pages) and excerpt in pages[page - 1]})
    by_key = {f.key: f for f in aon.facts}
    for fact in aon.facts:
        if fact.key == "ebitda":
            parts = ("net_income", "income_tax", "interest_expense", "depreciation", "amortization")
            total = sum(Decimal(str(by_key[k].amount)) for k in parts)
            rows.append({"case": aon.id, "kind": "derived", "locator": "EBITDA = sum of 5 cited lines",
                         "valid": Decimal(str(fact.amount)) == total})
            continue
        line = re.sub(r"\s*\(.*\)$", "", fact.label)
        pattern = re.escape(line) + r"\s*\(?\$?\s*" + re.escape(f"{fact.amount:,.0f}")
        rows.append({"case": aon.id, "kind": "fact", "locator": fact.source_locator,
                     "valid": re.search(pattern, tenk, re.IGNORECASE) is not None})
    for case_id in SYNTHETIC_CASES:
        for citation in catalog[case_id].rule.citations:
            rows.append({"case": case_id, "kind": "clause", "locator": citation.locator,
                         "valid": None, "note": "synthetic agreement; no source document"})
    anchors = []
    cache: dict[Path, str] = {}
    for label in _labels():
        for span in label["source_spans"]:
            path = _raw(span["source_path"])
            text = cache.setdefault(path, _source_text(path)) if path.is_file() else ""
            anchors.append({"label": label["label_id"], "source": span["source_path"],
                            "valid": span["anchor_text"] in text})
    verifiable = [r for r in rows if r["valid"] is not None]
    return {"rows": rows, "gold_anchors": anchors,
            "valid": sum(r["valid"] for r in verifiable), "total": len(verifiable),
            "unverifiable_synthetic": len(rows) - len(verifiable),
            "gold_anchors_valid": sum(a["valid"] for a in anchors),
            "gold_anchors_total": len(anchors)}


# --------------------------------------------------------------------------
# 3. golden calculations
# --------------------------------------------------------------------------

GOLDEN = [
    ("aurora-net-leverage", None, "DRAFT_COMPLIANT", "3.14", "3.50", None),
    ("beacon-gross-leverage", None, "DRAFT_BREACH", "4.17", "4.00", None),
    ("beacon-amendment", None, "DRAFT_COMPLIANT", "4.17", "4.25", None),
    ("meridian-evidence-gap", None, "NEEDS_REVIEW", "3.14", "3.50", ["ADJUSTMENT_EVIDENCE_REQUIRED"]),
    ("meridian-evidence-gap", APPROVE, "DRAFT_COMPLIANT", "3.14", "3.50", None),
    ("meridian-evidence-gap", REJECT, "DRAFT_BREACH", "4.07", "3.50", None),
    # Aon: real extraction, proxies, period mismatch. The ratio is deliberately
    # not pinned -- it is never a verdict; only the refusal and threshold are.
    ("aon-term-loan-leverage", None, "NEEDS_REVIEW", None, "4.00", ["FINANCIAL_PERIOD_MISMATCH"]),
]


def golden_calculations() -> dict:
    catalog = build_demo_catalog()
    rows = []
    for case_id, request, status, ratio, threshold, blocking in GOLDEN:
        result = _run(case_id, request, catalog)
        got = {"status": result.status.value,
               "ratio": None if result.calculation.ratio is None else money_str(result.calculation.ratio),
               "threshold": money_str(result.calculation.threshold),
               "blocking": _blocking_codes(result)}
        expected = {"status": status, "ratio": ratio, "threshold": threshold, "blocking": blocking}
        match = (got["status"] == status and got["threshold"] == threshold
                 and (ratio is None or got["ratio"] == ratio)
                 and (blocking is None or got["blocking"] == blocking))
        if case_id == "beacon-amendment":
            match = match and money_str(result.calculation.original_threshold) == "4.00"
        rows.append({"case": case_id, "request": (request or {}).get("reviewer_decision", "pending"),
                     "expected": expected, "got": got, "match": match})
    return {"rows": rows, "match": sum(r["match"] for r in rows), "total": len(rows)}


# --------------------------------------------------------------------------
# 4. false passes
# --------------------------------------------------------------------------

def _blocked_condition_runs() -> list[tuple[str, str, dict | None, dict]]:
    """(condition, case_id, request, catalog) where a verdict must be withheld."""
    runs = [
        ("unsupported add-back, no reviewer decision", "meridian-evidence-gap", None, build_demo_catalog()),
        ("financial period precedes test period", "aon-term-loan-leverage", None, build_demo_catalog()),
        ("approve add-back without reviewer name", "meridian-evidence-gap",
         {"reviewer_decision": "approve_addback"}, build_demo_catalog()),
        ("approve add-back without rationale", "meridian-evidence-gap",
         {"reviewer_decision": "approve_addback", "reviewer_name": "A. Treasurer"}, build_demo_catalog()),
    ]
    catalog = build_demo_catalog()
    for document in catalog["aurora-net-leverage"].documents:
        document.controlling = False
    runs.append(("no controlling agreement version", "aurora-net-leverage", None, catalog))
    catalog = build_demo_catalog()
    case = catalog["beacon-gross-leverage"]
    case.facts = [f for f in case.facts if f.key != "operating_leases"]
    runs.append(("required fact missing (never treated as zero)", "beacon-gross-leverage", None, catalog))
    catalog = build_demo_catalog()
    for fact in catalog["beacon-gross-leverage"].facts:
        if fact.key == "ebitda":
            fact.amount = 0
    runs.append(("zero denominator", "beacon-gross-leverage", None, catalog))
    catalog = build_demo_catalog()
    catalog["aurora-net-leverage"].rule.supported = False
    catalog["aurora-net-leverage"].rule.unsupported_reason = "No calculator for this rule in v1."
    runs.append(("no evaluated covenant (empty set cannot pass)", "aurora-net-leverage", None, catalog))
    return runs


def false_passes() -> dict:
    rows = []
    for condition, case_id, request, catalog in _blocked_condition_runs():
        result = _run(case_id, request, catalog)
        rows.append({"condition": condition, "case": case_id, "status": result.status.value,
                     "blocking": _blocking_codes(result),
                     "false_pass": result.status == DraftStatus.COMPLIANT})
    # Invariant over every run in this harness: COMPLIANT never co-occurs with a blocker.
    all_runs = [_run(c, r, build_demo_catalog()) for c, r, *_ in GOLDEN]
    all_runs += [_run(c, r, cat) for _, c, r, cat in _blocked_condition_runs()]
    compliant_with_blocker = sum(
        r.status == DraftStatus.COMPLIANT and bool(r.blocking_issues) for r in all_runs)
    return {"rows": rows, "false_passes": sum(r["false_pass"] for r in rows),
            "blocked_condition_runs": len(rows),
            "compliant_with_blocker": compliant_with_blocker, "all_runs": len(all_runs)}


# --------------------------------------------------------------------------
# 5. unsupported detection through the real upload -> pipeline path
# --------------------------------------------------------------------------

UPLOADS = [
    # (relative raw path, media type, role, issuer, expectation)
    ("pdf-fixtures/disney-credit-agreement.pdf", "application/pdf", "credit_agreement", "non-aon"),
    ("pdf-fixtures/citizens-credit-agreement.pdf", "application/pdf", "credit_agreement", "non-aon"),
    ("sec/celanese/2024-second-amendment-revolving.html", "text/html", "amendment", "non-aon"),
    ("sec/celanese/2024-third-amendment-term-loan.html", "text/html", "amendment", "non-aon"),
    ("sec/aon/2024-term-loan-credit-agreement.html", "text/html", "credit_agreement", "aon-html"),
    ("pdf-fixtures/aon-credit-agreement.pdf", "application/pdf", "credit_agreement", "aon-pdf-control"),
]


def _pipeline_upload(rel: str, media: str, role: str) -> dict:
    data = (RAW / rel).read_bytes()
    pipeline = CasePipeline(None, MemoryStorageAdapter())  # fresh: no case-document fallback
    version = pipeline.documents.upload(
        organization_id="eval-org", user_id="eval", case_id="eval-case", filename=Path(rel).name,
        content_type=media, data=data, document_role=role, title=Path(rel).stem)
    job = SimpleNamespace(id="job-eval", case_id="eval-case", revision_id="rev-1",
                          payload={"document_id": version.document_id})
    pipeline.begin(job)
    result = pipeline.run(job, on_progress=lambda: None)
    artifacts = {a["artifact_type"]: a["payload"] for a in pipeline.artifacts_for("eval-case", "rev-1")}
    manifest = artifacts["evidence_manifest"]
    calc = artifacts.get("calculation")
    return {
        "classify_upload": classify_upload(media, data),
        "run_status": result["status"],
        "extraction_state": manifest["extraction_state"],
        "rule_source": manifest["sources"]["rule"]["kind"],
        "calculation": None if calc is None else {
            "ratio": calc["ratio"], "threshold": calc["threshold"],
            "fact_source": calc["fact_source"]["kind"],
            "period_matches": calc["period_check"]["matches"]},
    }


def unsupported_detection() -> dict:
    rows = []
    for rel, media, role, kind in UPLOADS:
        if not (RAW / rel).is_file():
            rows.append({"document": rel, "kind": kind, "run_status": "SKIPPED", "reason": "file missing"})
            continue
        row = {"document": rel, "kind": kind, **_pipeline_upload(rel, media, role)}
        row["verdict_issued"] = row["run_status"] == "completed"
        rows.append(row)
    non_aon = [r for r in rows if r["kind"] == "non-aon" and r["run_status"] != "SKIPPED"]
    control = next((r for r in rows if r["kind"] == "aon-pdf-control"), {})
    aon_html = next((r for r in rows if r["kind"] == "aon-html"), {})
    return {"rows": rows,
            "non_aon_total": len(non_aon),
            "non_aon_unsupported": sum(r["extraction_state"] == "unsupported" for r in non_aon),
            "non_aon_verdicts": sum(r["verdict_issued"] for r in non_aon),
            "control_completed": control.get("run_status") == "completed",
            "control_period_matches": (control.get("calculation") or {}).get("period_matches"),
            "aon_html_unsupported": aon_html.get("extraction_state") == "unsupported"}


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def evaluate(uploads: bool = True) -> dict:
    report = {
        "extraction_vs_gold": extraction_vs_gold(),
        "span_validity": span_validity(),
        "golden_calculations": golden_calculations(),
        "false_passes": false_passes(),
    }
    if uploads:
        report["unsupported_detection"] = unsupported_detection()
    report["ok"] = (report["golden_calculations"]["match"] == report["golden_calculations"]["total"]
                    and report["false_passes"]["false_passes"] == 0
                    and report["false_passes"]["compliant_with_blocker"] == 0)
    return report


def _table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def render_markdown(report: dict) -> str:
    e, s, g, f = (report[k] for k in ("extraction_vs_gold", "span_validity",
                                      "golden_calculations", "false_passes"))
    u = report.get("unsupported_detection")
    summary = [
        ["Extraction vs gold (supported labels)", f"{e['PASS']}/{e['supported']} PASS",
         f"{e['UNSUPPORTED']}/{e['total']} labels unsupported by the single-shape parser; "
         f"{e['FAIL']} FAIL; {e['SKIPPED']} skipped"],
        ["Cited spans that resolve in the source (Aon case)", f"{s['valid']}/{s['total']}",
         f"{s['unverifiable_synthetic']} synthetic-case citations have no source document"],
        ["Gold anchors that resolve in data/raw/", f"{s['gold_anchors_valid']}/{s['gold_anchors_total']}",
         "same check as tests/test_dataset_gate.py"],
        ["Golden calculations matching", f"{g['match']}/{g['total']}",
         "status + threshold (+ ratio where pinned; Aon ratio is never a verdict)"],
        ["False passes on blocked-condition runs", f"{f['false_passes']}/{f['blocked_condition_runs']}",
         "observed result on curated cases, not proof"],
        ["DRAFT_COMPLIANT with a blocking issue present", f"{f['compliant_with_blocker']}/{f['all_runs']}",
         "every run in this harness"],
    ]
    if u:
        summary += [
            ["Non-Aon uploads flagged unsupported (pipeline)", f"{u['non_aon_unsupported']}/{u['non_aon_total']}",
             f"verdicts issued on non-Aon documents: {u['non_aon_verdicts']}/{u['non_aon_total']}"],
            ["Aon PDF control run completed", str(u["control_completed"]).lower(),
             f"period_check.matches={str(u['control_period_matches']).lower()} -> arithmetic shown, no verdict"],
            ["Aon HTML (same agreement) unsupported", str(u["aon_html_unsupported"]).lower(),
             "known parser false negative: PDF layout only"],
        ]
    parts = ["## Summary", _table(["Metric", "Result", "Denominator / note"], summary)]
    parts += ["\n## 1. Extraction vs gold", _table(
        ["Label", "Result", "Compared / reason"],
        [[r["label"], r["result"],
          ", ".join(f"{k}={'ok' if v else 'FAIL'}" for k, v in r["checks"].items())
          if "checks" in r else r.get("reason", "") + (
              f"; run lists interest coverage as an excluded obligation: "
              f"{str(r['detected_as_unsupported_obligation']).lower()}"
              if "detected_as_unsupported_obligation" in r else "")] for r in e["rows"]])]
    parts += ["\n## 2. Span validity", _table(
        ["Case", "Kind", "Locator", "Valid"],
        [[r["case"], r["kind"], r["locator"][:70],
          "n/a (synthetic)" if r["valid"] is None else r["valid"]] for r in s["rows"]])]
    parts += ["\n## 3. Golden calculations", _table(
        ["Case", "Decision", "Expected", "Got", "Match"],
        [[r["case"], r["request"],
          f"{r['expected']['status']} ratio={r['expected']['ratio']} thr={r['expected']['threshold']}",
          f"{r['got']['status']} ratio={r['got']['ratio']} thr={r['got']['threshold']} "
          f"blocking={r['got']['blocking']}", r["match"]] for r in g["rows"]])]
    parts += ["\n## 4. False passes", _table(
        ["Blocking condition", "Case", "Status", "Blocking codes", "False pass"],
        [[r["condition"], r["case"], r["status"], ", ".join(r["blocking"]), r["false_pass"]]
         for r in f["rows"]])]
    if u:
        parts += ["\n## 5. Unsupported detection (upload -> CasePipeline, memory mode)", _table(
            ["Document", "classify_upload", "Run status", "Extraction state", "Rule source", "Calculation"],
            [[r["document"], r.get("classify_upload", ""), r["run_status"], r.get("extraction_state", ""),
              r.get("rule_source", ""), r.get("calculation") or "none"] for r in u["rows"]])]
    parts.append(f"\nExit status: {0 if report['ok'] else 1}")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    if not AON_PDF.is_file():
        print(f"data/raw fixtures missing at {RAW}; nothing to evaluate", file=sys.stderr)
        return 2
    report = evaluate()
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render_markdown(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
