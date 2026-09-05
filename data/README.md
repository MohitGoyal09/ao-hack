# Covenant Certificate Data

This folder contains public-company filing material selected for parser, retrieval, cross-reference, financial-period, and amendment tests.

Read `case-readiness.json` and `../docs/implementation-contract.md` first. No package currently establishes a reviewed, temporally coherent full covenant verdict. The financial files precede the corresponding selected agreements. Existing sources are development material, not an untouched holdout set.

## Rules

- `raw/` is immutable source material. Do not edit these files.
- `annotations/` holds proposed labels with status `PROPOSED`.
- `gold/` holds reviewed labels only. Current scope is extraction-only
  (10 labels reviewed 2026-09-05: threshold schedules, ratio definitions,
  interest-coverage covenant text for unsupported-detection, period-mismatch
  refusals, one synthetic wrong-facility test). No label claims a verdict.
- `derived/` holds computed artifacts backing those labels (threshold tables,
  definition maps, mismatch findings, split plan), traceable to `raw/`.
- A public filing is evidence, not a gold answer.
- Do not publish extracted legal conclusions as professional advice.
- Recheck redistribution rights before making the repository public. The current repository is private.

## Selected packages

### Aon

Files: 2024 term-loan agreement, 2023 Form 10-K, SEC financial workbook, and PDF parser fixture.

Why selected: nested Adjusted EBITDA definitions, pro forma specified transactions, four-quarter measurement periods, leverage step-downs, and a compliance-certificate form reference. This is the primary extraction candidate. The 2023 financials do not establish compliance for a post-activation test under the 2024 agreement; obtain period-matched evidence and the actual certificate body.

### Citizens

Files: 2021 Q1 Form 10-Q, SEC financial workbook, and PDF parser fixture.

Why selected: leverage, pro forma basis, financial reporting requirements, and a named compliance-certificate exhibit. The original agreement URL still needs direct SEC provenance resolution, so its PDF is a parser fixture and not yet a gold legal source.

### Walt Disney

Files: 2024 364-day credit agreement, 2023 Form 10-K, SEC financial workbook, and PDF parser fixture.

Why selected: a distinct rolling-four-quarter interest-coverage covenant. In v1 use it for extraction and unsupported-covenant detection; it does not prove implemented interest-coverage calculations or holdout performance.

### Celanese

Files: February 2024 second and third amendments.

Why selected: covenant relief periods, test-date definitions, and dated leverage-threshold schedules. The second amendment concerns the revolving facility; the third concerns the term loan. Never chain these together. Use them for threshold extraction and wrong-facility rejection; acquire each facility's governing chain before precedence testing.

## Demonstration design

1. Complete one issuer/facility/test-date package and review its labels.
2. Prepare a draft calculation, then add a verified applicable amendment or clearly labelled controlled update.
3. Show affected dependencies, invalidated approvals, evidence review and a revised draft package.
4. Use intentionally withheld evidence as a labelled refusal test.
5. Label a shared-financial-packet comparison across different borrowers as hypothetical. Never claim an actual issuer breach from that experiment.

## Provenance

Original SEC URLs and SHA-256 hashes are stored in `manifest.json`.
