# Evaluation

How Covenant Certificate is measured today, the actual numbers, and what the
numbers do **not** show. Every count carries its denominator. Nothing here is a
holdout result, a user study, or a live-model accuracy figure; see
[What is not measured](#what-is-not-measured).

The harness is `apps/api/scripts/eval.py`. It is deterministic and offline
(stdlib + the product's own `src.covenant` modules; no model, network, or
database). Its JSON output is byte-identical across runs. The unit test
`apps/api/tests/test_eval_harness.py` runs sections 1-4 in-process on every
`unittest discover`, so a regression in any of them turns the suite red.

## Method

| # | Section | What is compared | Denominator |
|---|---|---|---|
| 1 | Extraction vs gold | Each reviewed label in `data/gold/*.json` is run against the matching extractor: Section 6.14(b) thresholds and the Section 1.01 definition via `extract_aon_rule` on the Aon PDF; the period-mismatch label via `extract_aon_financials` on the 10-K plus the workflow's refusal. Expected values come from the label's verbatim `anchor_text` (thresholds) and the reviewed `data/derived/` tables (numerator/denominator names), and each anchor must sit on the page the product cites. Labels the v1 single-shape parser cannot read are reported `UNSUPPORTED`, never dropped. | 10 labels; 3 supported by the parser |
| 2 | Citation/span validity | Every citation the product shows for the real-source case must resolve: the clause excerpt is found on the cited PDF page, each financial line label and amount co-occur in the 10-K text, and computed EBITDA equals the sum of its five cited lines. Gold anchors are re-checked against `data/raw/` (same check as `tests/test_dataset_gate.py`). Synthetic cases (Aurora, Beacon, Meridian) have no source document and are listed as unverifiable, not counted as valid. | 9 verifiable spans; 14 gold anchors; 8 synthetic |
| 3 | Golden calculations | Curated cases through `build_demo_workflow().run(...)`: status, threshold and (where pinned) ratio. Aurora 3.14 compliant; Beacon 4.17 breach; Beacon amendment threshold 4.25 (original 4.00); Meridian pending -> review, approved -> 3.14 compliant, rejected -> 4.07 breach; Aon -> `NEEDS_REVIEW` with exactly `FINANCIAL_PERIOD_MISMATCH` at the 4.00 Q1-2024 tier. The Aon ratio is deliberately not pinned: it is arithmetic on proxies, never a verdict. | 7 runs |
| 4 | False passes | Runs with a known blocking condition (missing add-back evidence, period mismatch, decision without reviewer name or rationale, no controlling document, missing required fact, zero denominator, no evaluated covenant) must not produce `DRAFT_COMPLIANT`. A second invariant checks every run in the harness: `DRAFT_COMPLIANT` never co-occurs with a blocking issue. | 8 blocked-condition runs; 15 runs total |
| 5 | Unsupported detection | Real documents pushed through the production path in memory mode (`DocumentService.upload` -> `CasePipeline.run`): Disney and Citizens credit-agreement PDFs and both Celanese amendment HTMLs must end `waiting_review` / `unsupported` with no calculation. Controls: the Aon PDF completes (rule from the upload, facts labelled `bundled_fixture`, `period_check.matches=false`); the HTML form of the same Aon agreement is also reported. | 4 non-Aon documents; 2 controls |

The script exits 1 if any golden calculation mismatches or a false pass exists.

### Why the gold is extraction-only

The ten reviewed labels (`data/gold/`, reviewed 2026-09-05) cover threshold
schedules, a ratio definition, interest-coverage text for
unsupported-detection, period-mismatch refusals and one synthetic
wrong-facility test. None claims a verdict, because no bundled package is
temporally coherent: every available financial filing predates its agreement
(`data/derived/period-mismatch-findings.json`, `data/case-readiness.json`).
A calculation label would therefore be labelling a number the product itself
refuses to certify.

## Results

Produced by `uv run python scripts/eval.py` on 2026-09-06 (about 66 s; three
100-page PDFs are parsed with pdfplumber). The script is the source of truth;
re-run it rather than trusting this copy.

| Metric | Result | Denominator / note |
|---|---|---|
| Extraction vs gold (supported labels) | 3/3 PASS | 7/10 labels unsupported by the single-shape parser; 0 FAIL; 0 skipped |
| Cited spans that resolve in the source (Aon case) | 9/9 | 8 synthetic-case citations have no source document |
| Gold anchors that resolve in data/raw/ | 14/14 | same check as tests/test_dataset_gate.py |
| Golden calculations matching | 7/7 | status + threshold (+ ratio where pinned; Aon ratio is never a verdict) |
| False passes on blocked-condition runs | 0/8 | observed result on curated cases, not proof |
| DRAFT_COMPLIANT with a blocking issue present | 0/15 | every run in this harness |
| Non-Aon uploads flagged unsupported (pipeline) | 4/4 | verdicts issued on non-Aon documents: 0/4 |
| Aon PDF control run completed | true | period_check.matches=false -> arithmetic shown, no verdict |
| Aon HTML (same agreement) unsupported | true | known parser false negative: PDF layout only |

### 1. Extraction vs gold

| Label | Result | Compared / reason |
|---|---|---|
| aon-2024-interest-coverage-001 | UNSUPPORTED | no interest-coverage extractor in v1; the Aon run lists interest coverage as an excluded obligation: true |
| aon-2024-lev-definition-001 | PASS | numerator_in_formula, denominator_in_formula, anchor_in_extracted_excerpt, anchor_on_cited_page (PDF p. 10), comparator |
| aon-2024-lev-threshold-001 | PASS | thresholds_in_order [4.00, 3.75, 3.25], derived_table_agrees, anchor_on_cited_page (PDF p. 56), section 6.14(b) |
| aon-2024-period-mismatch-001 | PASS | financials_extracted (7 facts), fact_period_is_fy2023, filing_anchor_in_10k, period_precedes_first_test, run_refuses_verdict, refusal_names_both_periods |
| celanese-revolver-threshold-001 | UNSUPPORTED | single-shape parser: v1 extracts only the Aon Section 6.14(b) PDF layout |
| celanese-termloan-threshold-001 | UNSUPPORTED | same |
| celanese-wrong-facility-001 | UNSUPPORTED | same (no facility-chain model exists yet) |
| citizens-2021-period-mismatch-001 | UNSUPPORTED | same |
| disney-2024-interest-coverage-001 | UNSUPPORTED | same |
| disney-2024-period-mismatch-001 | UNSUPPORTED | same |

### 2. Span validity (Aon case)

| Kind | Locator | Valid |
|---|---|---|
| clause | §6.14(b), PDF p. 56 | true |
| clause | §1.01, PDF p. 10 | true |
| fact | Note 15 — Debt: Total debt at December 31, 2023 (11,199) | true |
| fact | Consolidated Statements of Income — Net income (2,628) | true |
| fact | Consolidated Statements of Income — Income tax expense (541) | true |
| fact | Consolidated Statements of Income — Interest expense (484) | true |
| fact | Consolidated Statements of Income — Depreciation of fixed assets (167) | true |
| fact | Consolidated Statements of Income — Amortization and impairment of intangible assets (89) | true |
| derived | EBITDA = sum of 5 cited lines (3,909) | true |

Eight citations on the synthetic Aurora/Beacon/Meridian agreements are
hand-typed against agreements that do not exist as documents; they are
listed as `n/a (synthetic)` and excluded from the 9/9.

### 3. Golden calculations

| Case | Decision | Expected | Got | Match |
|---|---|---|---|---|
| aurora-net-leverage | pending | DRAFT_COMPLIANT 3.14 vs 3.50 | DRAFT_COMPLIANT 3.14 vs 3.50 | true |
| beacon-gross-leverage | pending | DRAFT_BREACH 4.17 vs 4.00 | DRAFT_BREACH 4.17 vs 4.00 | true |
| beacon-amendment | pending | DRAFT_COMPLIANT 4.17 vs 4.25 (original 4.00) | same | true |
| meridian-evidence-gap | pending | NEEDS_REVIEW 3.14 vs 3.50, ADJUSTMENT_EVIDENCE_REQUIRED | same | true |
| meridian-evidence-gap | approve_addback | DRAFT_COMPLIANT 3.14 vs 3.50 | same | true |
| meridian-evidence-gap | reject_addback | DRAFT_BREACH 4.07 vs 3.50 | same | true |
| aon-term-loan-leverage | pending | NEEDS_REVIEW, thr 4.00, FINANCIAL_PERIOD_MISMATCH | NEEDS_REVIEW 2.86 vs 4.00, FINANCIAL_PERIOD_MISMATCH | true |

### 4. False passes

| Blocking condition | Case | Status | Blocking codes |
|---|---|---|---|
| unsupported add-back, no reviewer decision | meridian-evidence-gap | NEEDS_REVIEW | ADJUSTMENT_EVIDENCE_REQUIRED |
| financial period precedes test period | aon-term-loan-leverage | NEEDS_REVIEW | FINANCIAL_PERIOD_MISMATCH |
| approve add-back without reviewer name | meridian-evidence-gap | NEEDS_REVIEW | REVIEWER_IDENTITY_REQUIRED, REVIEWER_RATIONALE_REQUIRED |
| approve add-back without rationale | meridian-evidence-gap | NEEDS_REVIEW | REVIEWER_RATIONALE_REQUIRED |
| no controlling agreement version | aurora-net-leverage | NEEDS_REVIEW | DOCUMENT_PRECEDENCE_UNRESOLVED |
| required fact missing (never treated as zero) | beacon-gross-leverage | NEEDS_REVIEW | MISSING_FINANCIAL_FACT |
| zero denominator | beacon-gross-leverage | NEEDS_REVIEW | NO_EVALUATED_COVENANTS, ZERO_DENOMINATOR |
| no evaluated covenant (empty set cannot pass) | aurora-net-leverage | NEEDS_REVIEW | NO_EVALUATED_COVENANTS |

0/8 false passes is an observed result on curated cases, not proof that the
policy is complete.

### 5. Unsupported detection (upload -> CasePipeline, memory mode)

| Document | classify_upload | Run status | Extraction state | Calculation |
|---|---|---|---|---|
| pdf-fixtures/disney-credit-agreement.pdf | pending | waiting_review | unsupported | none |
| pdf-fixtures/citizens-credit-agreement.pdf | pending | waiting_review | unsupported | none |
| sec/celanese/2024-second-amendment-revolving.html | pending | waiting_review | unsupported | none |
| sec/celanese/2024-third-amendment-term-loan.html | pending | waiting_review | unsupported | none |
| sec/aon/2024-term-loan-credit-agreement.html | pending | waiting_review | unsupported | none (parser false negative) |
| pdf-fixtures/aon-credit-agreement.pdf (control) | pending | completed | supported | ratio 2.86, threshold 4.00, fact_source bundled_fixture, period_matches false |

`classify_upload` only screens for OCR need (`pending` / `needs_ocr`); the
refusal happens in the pipeline, where the parser raises instead of guessing.
The Citizens PDF is the interesting case: it does contain a
"(b) Consolidated Leverage Ratio" heading (p. 55) but a different threshold
syntax, and the extractor refused rather than returning a partial schedule.

## Reproduce

```bash
cd apps/api && uv sync --frozen
uv run python scripts/eval.py            # Markdown, exit 1 on golden mismatch / false pass
uv run python scripts/eval.py --json     # byte-stable JSON
uv run python -m unittest discover -s tests   # includes tests/test_eval_harness.py (sections 1-4)
```

No `.env`, key, database, or network is needed. `COVENANT_DATA_ROOT` may point
at another `data/raw`-shaped directory.

## What is not measured

- **No holdout.** Every document in `data/raw/` is development material the
  parser was written against (`data/derived/split-plan.json`: held-out set is
  empty). 3/3 is a regression result on the family the code targets, not
  generalisation.
- **No calculation gold.** The extracted 10-K amounts are checked for
  label-and-amount co-occurrence in the source, not against reviewer-labelled
  values; the Aon ratio is on line-item proxies for contract-defined terms.
- **No user validation.** No treasury or controllership user has run the
  workflow. Nothing here measures time saved, error rate versus a manual
  certificate, or completion rate.
- **No live-model accuracy.** The copilot's tool-calling path is not part of
  the harness; every measured path is deterministic Python. Model behaviour
  is described in `agent-docs`/README material, not scored.
- **One reviewer.** The ten gold labels were proposed and reviewed by the same
  worker on the same day; there is no second-reviewer agreement figure.
- **Parser coverage is one shape.** 7/10 labels are outside it; the HTML form
  of the very agreement the parser handles is refused. Precision is measured;
  recall over real-world agreement layouts is not.

## What would make this a real evaluation

1. Acquire one untouched agreement family (different issuer, layout and
   drafting house) as holdout; report extraction precision/recall on it
   without touching the parser after the first run.
2. Add reviewer-labelled calculation gold on a temporally coherent package
   (agreement, matching-period financials, add-back support) so the harness
   can pin a ratio that is a real draft, and add a second reviewer with an
   agreement figure.
3. Add extractors for at least the Celanese schedule-table shape and the
   interest-coverage clause so "unsupported" becomes a measured recall, and a
   facility-chain check so `celanese-wrong-facility-001` is exercised.
4. Run a versioned model-eval job: the copilot on fixed prompts with the tools
   mocked, scoring that it never emits a number the calculator did not
   produce; record model id, prompt hash and pass rate per version.
5. Wire `scripts/eval.py --json` into CI and diff the JSON against the
   committed baseline on every parser or policy change.
