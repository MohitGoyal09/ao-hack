# Covenant Certificate Data

This folder contains public-company filing material selected for parser, retrieval, cross-reference, financial-period, and amendment tests.

## Rules

- `raw/` is immutable source material. Do not edit these files.
- `derived/` will contain normalized text, tables, page maps, and definition graphs.
- `gold/` will contain expert-reviewed labels only.
- A public filing is evidence, not a gold answer.
- Do not publish extracted legal conclusions as professional advice.
- Recheck redistribution rights before making the repository public. The current repository is private.

## Selected packages

### Aon

Files: 2024 term-loan agreement, 2023 Form 10-K, SEC financial workbook, and PDF parser fixture.

Why selected: nested Adjusted EBITDA definitions, pro forma specified transactions, four-quarter measurement periods, leverage step-downs, and a compliance-certificate form reference. This is the primary maximum-leverage case.

### Citizens

Files: 2021 Q1 Form 10-Q, SEC financial workbook, and PDF parser fixture.

Why selected: leverage, pro forma basis, financial reporting requirements, and a named compliance-certificate exhibit. The original agreement URL still needs direct SEC provenance resolution, so its PDF is a parser fixture and not yet a gold legal source.

### Walt Disney

Files: 2024 364-day credit agreement, 2023 Form 10-K, SEC financial workbook, and PDF parser fixture.

Why selected: a distinct rolling-four-quarter interest-coverage covenant. Use it to prove that the schema is not hard-coded only for leverage.

### Celanese

Files: February 2024 second and third amendments.

Why selected: covenant relief periods, test-date definitions, and a dated leverage-threshold schedule. Use it for amendment precedence and threshold-table extraction. Do not treat it as a complete case until the original agreement and prior amendments are added.

## Demonstration design

1. Compile the Aon agreement and map its real filing evidence.
2. Apply one controlled financial packet to two reviewed agreement definitions to produce opposite outcomes.
3. Use Celanese to show that an amendment changes the active threshold by test date.
4. Remove evidence for one adjustment and require `NEEDS_REVIEW`.

## Provenance

Original SEC URLs and SHA-256 hashes are stored in `manifest.json`.
