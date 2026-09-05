# Covenant reporting implementation contract

Revision: 2026-09-05. Status: approved product direction; implementation and domain validation remain outstanding.

This document supersedes conflicting scope, state, data, and execution-order statements in the earlier architecture and plans. Read it before either implementation plan.

## Product and first milestone

Build a borrower-side covenant reporting workspace for Track 2. It prepares a draft calculation package, responds to a new amendment or financial update, resolves evidence exceptions with a reviewer, and produces a revised draft for officer approval. AO remains the build tool.

The runtime remains Python, FastAPI, LangGraph, Supabase Postgres/Auth/private Storage, LiteLLM Proxy, and Neatlogs. The frontend uses the selected CopilotKit starter and custom finance components over AG-UI. Reuse the runtime libraries; do not build another general harness.

First implement maximum gross or net leverage under the selected agreement's definitions. Discover and list all other candidate obligations but mark unsupported calculations explicitly. A passed supported ratio must never be labelled full agreement compliance. Interest coverage is a later extension and an unsupported-covenant detection test in v1.

First milestone: one authenticated case with immutable documents and a sourced leverage calculation; adding evidence or an amendment creates a new revision, invalidates affected outputs, and resumes the workflow through human review. Preserve the prior revision for comparison. A final draft package requires approval of the exact current revision.

## Dataset gate before interpretation work

The current corpus is source material for component tests, not a complete gold certification package.

| Package | Permitted present use | Missing prerequisite for an actual covenant verdict |
|---|---|---|
| Aon February 2024 agreement and 2023 financials | Definitions, threshold extraction, period mismatch tests | Closing/activation evidence, financials for the actual selected test period, relevant amendment chain, adjustment support, actual certificate form |
| Disney March 2024 agreement and 2023 financials | Definition extraction, unsupported interest-coverage detection | Current-to-test-date agreement package and compatible measurement-period financials; interest coverage implementation is outside v1 |
| Citizens May 2021 agreement PDF and Q1 2021 financials | Parser and mismatch tests | Primary exhibit provenance and subsequent applicable financial period; do not assume Q1 is a valid test under the later agreement |
| Celanese February 2024 exhibits | Amendment classification, threshold tables, wrong-facility rejection | Original and intervening documents for the chosen facility. Exhibit 10.1 is revolving-facility amendment 2; Exhibit 10.2 is term-loan amendment 3. These are separate chains |

An exhibit list mentioning a certificate form does not establish that the form is supplied. Verify its body and required officer statements. Financial workbooks and HTML from the same filing are two renderings, not independent corroboration.

For each case, record: case ID, issuer, borrower and facility identity, test date, agreement effective/closing date, source hashes, source URLs, financial period boundaries, governing document chain, included and missing certificate sections, and evidence gaps. Separate observed source facts from inferred interpretation.

Use one source of truth for labels: `data/gold/`. Store proposed labels under `data/annotations/` with status `PROPOSED`; only reviewed records may enter `data/gold/`. Every reviewed label carries reviewer identity, review date, rationale, source spans, and review scope. Extraction labels can be reviewed separately from legal interpretation or full calculation labels. Unknown results remain null with a reason.

Development, regression, and held-out sets must split by issuer/facility/agreement family. HTML/PDF duplicates and amendments from one family stay together. The documents already inspected while designing this product are development material, not untouched holdout data. Acquire a new agreement family for the final holdout.

The same-financials/two-agreements comparison is a labelled hypothetical when those contracts do not govern the same borrower and period. Controlled modifications and withheld evidence must be labelled synthetic or intentionally incomplete; never report these as a real issuer breach.

## State and authority

Store separate dimensions rather than one overloaded status:

- Run state: queued, running, waiting_review, completed, failed, cancelled.
- Per-covenant result: pass, fail, indeterminate, not_applicable, unsupported.
- Coverage: complete_for_declared_scope or incomplete, with assessed and excluded obligations listed.
- Package state: draft, ready_for_officer_review, approved_draft, superseded.

Legacy `DRAFT_COMPLIANT` means only a pass for the declared supported scope. `DRAFT_BREACH` means a calculated failed test requiring review, not a legal determination of default or lender remedies. Preserve computed failures even if another covenant is indeterminate. An empty set of evaluated covenants cannot pass.

An internal app approval is not an electronic signature or delivery to a lender. If `FINALIZED` is retained in implementation, it means a frozen internally approved draft, with unsigned statements disclosed. Required unsupported attestations prevent a lender-ready label; the app may still export a marked incomplete workpaper.

Human interpretation cannot rewrite a contract. Store interpretation, evidence acceptance, correction, and officer approval as different decision kinds. Default scope is case-only. Future-period reuse proposes prior mappings only after rechecking document version, period, entity and policy scope. It never copies old financial amounts or approval automatically.

## Change-aware rechecking

Introduce immutable `CaseRevision`, `ChangeSet`, `ImpactSet`, and `ApprovalBinding` records.

- `CaseRevision`: case ID, revision ID, parent revision, test date, input bundle hash, rulebook hash, mapping hash, calculation hash and coverage hash.
- `ChangeSet`: added/replaced document IDs, changed fact/decision IDs, source revision, target revision and event reason.
- `ImpactSet`: changed definitions, affected rules/facts, dependent calculations, invalidated decisions/artifacts and unaffected references.
- `ApprovalBinding`: actor, role, target revision and bundle hash, decision, reason, timestamp and superseding approval reference.

Dependency chain: source span -> definition or fact -> rule/mapping -> calculation -> review decision -> package. An amendment may also alter applicability or add a covenant, so rerun document precedence and covenant inventory before computing the affected dependency closure. If semantic impact is uncertain, rerun the whole supported analysis. A graph traversal alone cannot prove a legal interpretation.

When an input changes, atomically create a new revision and mark affected outputs stale. Show the previous result as historical until the new calculation passes validation. Old approvals stay in history but cannot authorize the new revision. Finalized artifacts remain immutable and are marked superseded when appropriate.

Review requests include revision ID, issue ID, expected bundle hash, evidence requirements and conditional impact. Apply a decision only if the current revision and issue still match; return HTTP 409 for a stale decision. A duplicate idempotency key with the same payload returns the original response; a different payload conflicts. Only the server resolves issues and authorizes graph resume.

## Contracts between backend and frontend

`POST /api/cases/{case_id}/revisions`: input includes expected parent revision, change kind and uploaded document/fact references; returns new revision ID and pending impact analysis. Financial corrections are versioned proposals, never arbitrary overwrites.

`GET /api/cases/{case_id}/revisions/{revision_id}/impact`: returns changed inputs, affected rule IDs, stale artifact IDs and review requirements.

`POST /api/review-issues/{issue_id}/resolve`: includes revision ID, expected bundle hash, decision kind, rationale, evidence references and idempotency key. Role and organization come from verified server identity.

`POST /api/cases/{case_id}/officer-approval`: binds approval to the current revision and exact package hash, after rechecking coverage and blocking issues in a transaction.

`GET /api/cases/{case_id}/snapshot`: returns revision, run state, per-covenant results, coverage, package state and last durable event sequence. Financial decimals are strings across JSON boundaries.

Persist domain events with case ID, revision ID, run ID, monotonic case sequence and artifact references. Use AG-UI standard lifecycle/state events; wrap custom names in its custom-event envelope. Names such as `INPUT_CHANGED`, `IMPACT_ANALYZED`, `RESULT_INVALIDATED`, `REVIEW_REQUIRED`, `RECALCULATION_COMPLETED`, `APPROVAL_INVALIDATED` and `PACKAGE_REVISED` are application events, not new protocol primitives. On reconnect retrieve the snapshot and replay subsequent durable events. The browser never authorizes a decision by changing shared state.

## Execution and persistence

Run CPU-heavy parsing outside the request event loop. Start with one API and one worker process from the same Python application/image. A Postgres job table provides queued work, leases, attempt counts and fencing tokens; do not add another workflow framework. LangGraph checkpoints preserve execution state but do not themselves schedule a restart after process death.

Only one active revision run per case may publish authoritative results. Persist node output, audit event and publication intent in the same transaction. Checkpoint advancement and business writes are not assumed atomic: retries reconcile through versioned output IDs and idempotency keys. A stale worker cannot publish after losing its lease. Client disconnect does not cancel a durable job; cancellation is a separate authenticated command.

Supabase SQL migrations are the sole owner of business-schema history. SQLAlchemy models map the schema; remove Alembic from the implementation dependency list. LangGraph checkpoint setup is separately versioned and run explicitly against the intended environment, never on every public request. No shared/cloud database is reset as a test prerequisite.

LiteLLM routes must pass structured-output and tool-call contract tests before selection. Require gateway authentication; keep provider keys at the proxy. Do not silently drop required schema/tool parameters. Record requested alias, actual model/provider, fallback, prompt version and input hash. Assign transient transport retries to one layer and bound total attempts; do not multiply SDK, proxy and graph retries. Budget enforcement remains an implementation task until tested, not a property established by a config file.

## Build order and evidence gates

1. **Dataset gate (Task 0):** catalogue gaps, create reviewed extraction labels and acquire one coherent test-date package. Foundation tasks may proceed concurrently; real compliance claims cannot.
2. **Foundation (Tasks 1-4):** authenticated case creation, private upload, revisions, immutable storage, parsing and provenance. Validate with current documents and synthetic service tests.
3. **First calculation (Tasks 5-8):** full definition resolution and sourced facts for one reviewed leverage case. Introduce gold assertions alongside each task rather than waiting until Task 14.
4. **Recheck and review (Tasks 9-11):** upload changed input, invalidate dependent results/approvals, resume the durable job, resolve evidence and publish the new revision.
5. **Draft package (Task 12):** render reviewed scope, evidence and required statements; officer approval binds to the exact version.
6. **Observability and proof (Tasks 13-15):** wire Neatlogs with payload capture disabled/redacted, aggregate stage tests, run held-out evaluation and full restart/review/recheck demonstration.

## Acceptance scenarios

| Scenario | Required observed result |
|---|---|
| Financial period precedes applicable testing date | Indeterminate with a specific missing-period request |
| Amendment belongs to another facility | Reject attachment to governing chain; retain source and explain mismatch |
| New threshold replaces the current threshold | New revision, affected calculation reruns, old approval invalidated |
| Amendment adds a covenant | Covenant inventory reruns; unsupported item stays visible and blocks complete coverage |
| Supported add-back lacks evidence | Request evidence; display any what-if as conditional and separate from actual result |
| Reviewer accepts evidence | Recompute and revalidate; preserve failed outcome if the calculation still fails |
| Two reviewers act on different revisions | Stale command rejected with 409; no lost update |
| Worker dies after persisting output | Retry reuses committed output, emits no duplicate decision or package |
| New reporting period | Prior mappings suggested, all period-specific amounts and approvals refreshed |
| Hypothetical comparison | Prominent hypothetical label; no claim about either issuer's actual compliance |

Report observed test counts and denominators. Zero false passes on a small dataset is an observed result, not proof of zero production risk. Measure source support and semantic correctness separately from citation presence; a real citation can still support the wrong conclusion. Evaluate the second model reviewer as another fallible component, not independent proof.

## Demo sequence

Open the prepared case and show its declared coverage and evidence. Upload a real applicable amendment or a clearly labelled controlled update. Highlight the affected definition/threshold and stale result. Recalculate, resolve a missing-evidence request, and regenerate the draft package. Show the old and new revisions and who approved the current one. Use the hypothetical two-agreement comparison as a supporting view after this workflow succeeds.

## Ready to start

Start Tasks 0 and 1. Task 1 ends at a tested application shell with mocked external failures and an explicit dependency-readiness report. The first real model smoke test requires configured LiteLLM credentials; the first persistence smoke test requires a selected Supabase development project. Acquire these through environment configuration without committing credentials. Domain labels and complete source packages remain explicit evidence gates, not reasons to postpone the shell or upload implementation.
