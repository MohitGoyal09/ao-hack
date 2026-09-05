# Covenant Certificate Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Track every step with its checkbox.

**Goal:** Build a borrower-side reporting workflow that prepares a sourced calculation package, rechecks it after changed inputs, resolves evidence exceptions, and produces a revised draft for officer approval.

**Architecture:** One FastAPI service runs a bounded LangGraph workflow. LLM nodes propose legal interpretations and financial mappings. Deterministic services own precedence, completeness, arithmetic, state changes, approvals, and finalization. Supabase is the authoritative database, Auth, and private file store. Neatlogs receives redacted operational traces only.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Pydantic 2, SQLAlchemy 2, psycopg 3, Supabase SQL migrations, Docling, LiteLLM Proxy, AG-UI, Neatlogs, pytest, Ruff, mypy.

**Spec:** `docs/covenant-certificate-backend-architecture.md`

**Controlling revision:** `docs/implementation-contract.md`. Read it first; it defines revision-bound approvals, precise status meanings, dataset restrictions and changed-input behavior. All module paths below resolve under `apps/api/src/covenant_certificate/`; test paths resolve under `apps/api/tests/` unless explicitly rooted elsewhere. Commits in task checklists are checkpoints when commit authorization applies, not automatic permission to push.

## Task 0: Establish document readiness and stage-level labels

**Files:** `data/case-readiness.json`, `data/annotations/`, `data/gold/`, `apps/api/tests/evals/test_dataset_manifest.py`.

- [ ] Validate hashes and classify each existing package using the readiness record. Keep financials that precede the selected test period as negative fixtures.
- [ ] Select one borrower, facility and post-activation test date. Acquire the applicable original agreement, intervening amendments, period financials, adjustment support and actual certificate body. Record any unavailable item explicitly.
- [ ] Keep Celanese revolving and term-loan facilities separate. Test that the wrong-facility amendment is rejected.
- [ ] Create proposed labels for definitions, threshold schedules, applicability and exact source locators; promote only reviewed labels to `data/gold/` with reviewer and scope metadata.
- [ ] Create calculation labels only when the full input period and adjustments are supported. Do not infer issuer compliance from a generic EBITDA reconstruction.
- [ ] Acquire a new issuer/agreement family for holdout. Existing inspected sources are development material.
- [ ] Define separate development tests for intentionally withheld evidence and hypothetical comparisons, with explicit labels.

Gate: Tasks 1-4 may start now. A claimed real-document verdict requires a coherent reviewed package. Each later agent task adds its own assertions from these labels; Task 14 aggregates them.

## Global constraints

- AO is a development tool and is not part of runtime.
- First workflow: borrower-side financial maintenance covenant certification.
- First covenant: maximum leverage ratio.
- The only analytical outcomes are `DRAFT_COMPLIANT`, `DRAFT_BREACH`, and `NEEDS_REVIEW`.
- Only an authenticated officer can move a certificate to `FINALIZED`.
- Models never perform final arithmetic or directly modify authoritative state.
- Backend model calls use LiteLLM aliases only. Provider model IDs and keys stay in gateway configuration.
- Every rule, fact, adjustment, and result needs source provenance.
- Missing evidence never defaults to zero and never produces compliance.
- Use `Decimal`, immutable source files, versioned artifacts, and private Storage.
- Every public table has RLS. No server secret uses a `NEXT_PUBLIC_` variable.

## Final module map

```text
apps/api/src/covenant_certificate/
├── api/routes/             cases, documents, reviews, artifacts
├── auth/                   Supabase token verification
├── domain/                 typed business models and enums
├── persistence/            SQLAlchemy sessions and scoped repositories
├── storage/                private Supabase Storage adapter
├── parsing/                Docling adapter, normalization, indexing
├── legal/                  classification, precedence, definitions, rules
├── financial/              facts, periods, mappings, evidence
├── calculation/            typed AST, compiler, evaluator, controls
├── review/                 deterministic policy and independent reviewer
├── workflows/              LangGraph state, nodes, routing, graph
├── events/                 audit publisher and AG-UI adapter
├── observability/          Neatlogs adapter
└── rendering/              certificate and evidence package
```

## Task 1: Replace the copied demo backend

**Files:** modify `apps/api/pyproject.toml`, `apps/api/main.py`; create `src/covenant_certificate/config.py`, `api/errors.py`, `tests/unit/test_config.py`, `tests/integration/test_health.py`; remove sample flight, todo, proverb, and CSV modules.

**Produces:** `Settings`, `create_app()`, `/health/live`, `/health/ready`.

- [ ] Write failing tests for required production configuration and secret-safe representations.
- [ ] Add and lock SQLAlchemy, psycopg, Supabase, multipart upload, Postgres checkpointer, JWT, structlog, pytest, Ruff, and mypy dependencies. Add Docling in Task 4 when its parser is exercised. Supabase SQL migrations own business schema history.
- [ ] Configure the OpenAI-compatible client against `LITELLM_BASE_URL` and test the `covenant-fast` and `covenant-strong` aliases.
- [ ] Verify strict structured output, tool calls, timeouts, authentication, and actual-provider reporting for each gateway route. Do not silently drop required parameters or declare budgets enforced before testing them.
- [ ] Implement settings, structured API errors, liveness, and dependency-aware readiness.
- [ ] Remove all sample business behavior while preserving the minimal AG-UI serving pattern.
- [ ] Run focused tests, `ruff check`, and `mypy src`.
- [ ] Commit `chore: replace sample agent with backend shell`.

## Task 2: Create the Supabase schema and RLS policies

**Files:** create a CLI-generated migration under `supabase/migrations/`; create `apps/api/src/covenant_certificate/persistence/database.py`, `models.py`, and `tests/integration/test_schema.py`.

**Produces:** transactional async database access and the authoritative data model.

- [ ] Use `supabase migration new initial_backend_schema`; do not invent the timestamp.
- [ ] Write a failing schema test for tables, foreign keys, indexes, constraints, and RLS.
- [ ] Create tables for organizations, memberships, cases, facilities, documents, document versions and spans, definition nodes and edges, covenant rules, thresholds, financial facts and dependencies, mappings, calculation plans and runs, review issues, human decisions, certificates, audit events, and model runs.
- [ ] Add case revisions, change sets, impact sets, approval bindings, durable jobs and event outbox records as specified in the implementation contract. Enforce one active publishing run per case and revision-aware writes.
- [ ] Use UUID keys, `timestamptz`, `numeric`, immutable version rows, and organization/case ownership.
- [ ] Add indexes for each case, document, rule, fact, issue, certificate, and event read path.
- [ ] Enable RLS on all public tables. Browser clients receive scoped reads only. Authoritative writes remain backend-mediated.
- [ ] Apply from zero locally, run Supabase advisors, and require the schema test to pass.
- [ ] Commit `feat: add supabase covenant schema`.

## Task 3: Add Supabase Auth, repositories, and private Storage

**Files:** create `auth/supabase.py`, `api/dependencies.py`, `storage/supabase.py`, `persistence/repositories/`, `tests/integration/test_auth.py`, and `test_storage.py`.

**Produces:** `CurrentUser`, `UnitOfWork`, `DocumentStorage`, case-scoped repositories.

- [ ] Reject missing, expired, malformed, and wrong-project tokens.
- [ ] Never use user-editable metadata for authorization.
- [ ] Enforce organization and case scope in every repository method.
- [ ] Create private bucket `covenant-private` and deny public listing or reads.
- [ ] Store objects at `{organization_id}/{case_id}/{document_id}/{sha256}/{safe_filename}`.
- [ ] Implement immutable upload and signed download. Do not upsert source files.
- [ ] Prove cross-organization database and Storage access fails.
- [ ] Commit `feat: add authenticated supabase persistence`.

## Task 4: Implement immutable document intake

**Files:** create `domain/documents.py`, `parsing/docling_adapter.py`, `normalizer.py`, `indexer.py`, `api/routes/documents.py`, and `tests/integration/test_document_intake.py`.

**Produces:** `ParsedDocument`, page-aware `SourceSpan`, `SourceTable`, exact-term and Postgres full-text indexes.

- [ ] Test PDF, DOCX, XLSX, duplicate hash, wrong MIME, oversized input, unsafe name, and parse failure.
- [ ] Stream upload while calculating SHA-256 and validating declared type.
- [ ] Store the original before parsing. Never execute macros or embedded content.
- [ ] Preserve page, heading path, table coordinates, bounding box, source hash, and parser version.
- [ ] Use exact search for defined terms and semantic search only as a recall aid.
- [ ] Emit persisted `DOCUMENT_ACCEPTED`, `DOCUMENT_PARSED`, and failure events.
- [ ] Commit `feat: add immutable document intake`.

## Task 5: Resolve legal document precedence

**Files:** create `legal/classifier.py`, `precedence.py`, `domain/cases.py`, `tests/unit/legal/test_precedence.py`, and `tests/evals/test_document_classification.py`.

**Produces:** `DocumentVersionChain` and `EffectiveClauseSet`.

- [ ] Classify agreement, amendment, waiver, consent, and certificate form with typed output and citations.
- [ ] Test two amendments, one-period waiver, future amendment, missing effective date, and conflict.
- [ ] Let the model propose metadata, then order and validate versions deterministically.
- [ ] Preserve original clauses and create derived effective clauses with links to all sources.
- [ ] Create `UNRESOLVED_PRECEDENCE` instead of guessing.
- [ ] Validate facility identity, effective dates and conditions; chronological ordering alone cannot establish controlling terms.
- [ ] Commit `feat: resolve agreement precedence`.

## Task 6: Compile recursive covenant definition graphs

**Files:** create `domain/definitions.py`, `domain/covenants.py`, `legal/discovery.py`, `definition_graph.py`, `rule_compiler.py`, `tests/unit/legal/test_definition_graph.py`, and `tests/evals/test_rule_compilation.py`.

**Produces:** `DefinitionGraph`, `CovenantRule`, `ThresholdSchedule`.

- [ ] Create fixtures for nested terms, includes, excludes, caps, conditions, step-downs, and cycles.
- [ ] Discover candidate maintenance covenants from operative sections and certificate schedules.
- [ ] Resolve terms recursively with visited-set cycle detection and a depth limit.
- [ ] Persist `REFERENCES`, `AMENDS`, `REPLACES`, `INCLUDES`, `EXCLUDES`, `CAPS`, and `CONDITIONAL_ON` edges.
- [ ] Compile maximum leverage into typed numerator, denominator, operator, threshold schedule, period, activation condition, and citations.
- [ ] Require provenance for every compiled field and a recall check against headings and certificate form.
- [ ] List unsupported covenants separately. Do not declare full agreement compliance when only leverage is evaluated; no discovered/supported tests must never become an empty pass.
- [ ] Commit `feat: compile covenant definition graphs`.

## Task 7: Extract and map financial facts

**Files:** create `domain/financial_facts.py`, `financial/extractor.py`, `periods.py`, `mapper.py`, `evidence.py`, `tests/unit/financial/test_periods.py`, and `tests/evals/test_fact_mapping.py`.

**Produces:** sourced `FinancialFact`, derived lineage, candidate `FactMapping`.

- [ ] Test instant, quarter, year-to-date, rolling-four-quarter, scale, currency, sign, and entity scope.
- [ ] Extract decimal facts with source span, period, currency, scale, entity, and confidence.
- [ ] Construct rolling periods only from compatible non-overlapping durations.
- [ ] Require schedules for add-backs and pro forma acquisition adjustments.
- [ ] Persist alternatives and create review issues when mapping is ambiguous.
- [ ] Block period, entity, currency, unit, and unsupported-adjustment mismatches.
- [ ] Commit `feat: map financial evidence to covenant terms`.

## Task 8: Build the safe calculation engine

**Files:** create `domain/calculations.py`, `calculation/ast.py`, `compiler.py`, `evaluator.py`, `controls.py`, and `tests/unit/calculation/`.

**Produces:** `CalculationPlan`, `CalculationRun`, `HeadroomResult`.

- [ ] Define a discriminated operation union for literals, facts, arithmetic, min/max, sum, conditions, caps, period aggregates, currency conversion, and comparisons.
- [ ] Test every operation, missing facts, divide by zero, rounding, caps, and deterministic serialization.
- [ ] Compile maximum net leverage without generated Python, JavaScript, SQL, shell, or `eval`.
- [ ] Evaluate with `Decimal` and record inputs, intermediates, output, threshold, operator, headroom, rounding, and code version.
- [ ] Prove unsupported inputs cannot produce compliance.
- [ ] Commit `feat: add deterministic covenant calculator`.

## Task 9: Add independent review and human decisions

**Files:** create `domain/reviews.py`, `review/policy.py`, `independent.py`, `api/routes/reviews.py`, `tests/unit/review/test_policy.py`, and `tests/integration/test_human_review.py`.

**Produces:** `ReviewIssue`, `HumanDecision`, controlled transitions.

- [ ] Encode blocking rules for precedence, definitions, evidence, periods, units, OCR risk, adjustments, control failure, and potential breach.
- [ ] Give the independent reviewer sources and structured results, but not the compiler’s hidden reasoning.
- [ ] Support approve, reject, correct mapping, request evidence, and mark unresolved.
- [ ] Record identity, role, reason, evidence, scope, timestamp, superseded decision, and before/after impact.
- [ ] Prevent an agent or unauthenticated request from resolving issues.
- [ ] Require a separate officer approval before finalization.
- [ ] Bind every decision to revision ID and input/package hash. Reject stale decisions with 409, preserve history, and never treat approval of evidence as permission to force a pass.

## Task 9A: Implement changed-input impact and invalidation

**Files:** `domain/revisions.py`, `review/approval_bindings.py`, `workflows/impact.py`, `tests/unit/test_impact.py`, `tests/integration/test_revision_decisions.py`.

**Interfaces:** `create_revision(case_id, expected_parent_revision_id, change_set) -> CaseRevision`; `analyze_impact(old_revision, new_revision) -> ImpactSet`. Both are organization-scoped services. Models may propose semantic changes; the services persist and enforce the validated dependency closure.

- [ ] Add immutable revision records and span-to-rule/fact-to-calculation-to-package dependency edges.
- [ ] On an amendment, recheck governing chain, applicability and covenant inventory before choosing which calculations to rerun.
- [ ] On new evidence or a financial correction, invalidate dependent mappings, calculations, review approvals and package readiness in one transaction.
- [ ] Reuse unaffected outputs only when their source and configuration hashes still match. Unknown impact triggers full supported-scope reanalysis.
- [ ] Preserve historical artifacts as superseded. Require approval of the newly generated package hash.
- [ ] Test added covenant, changed threshold, unchanged appendix, unsupported adjustment, stale approval, duplicate command and next-period mapping reuse without copying amounts.
- [ ] Commit `feat: add human review controls`.

## Task 10: Compose LangGraph with Supabase Postgres checkpoints

**Files:** create `workflows/state.py`, `nodes.py`, `routing.py`, `case_graph.py`, and `tests/graph/test_case_graph.py`.

**Produces:** resumable graph keyed by case ID.

- [ ] Keep IDs and summaries in graph state, not document bodies or complete database rows.
- [ ] Parse legal and financial branches in parallel after intake, then join at fact mapping.
- [ ] Configure the PostgreSQL checkpointer against Supabase.
- [ ] Interrupt on every material uncertainty and before officer approval.
- [ ] Test pass, breach, pause/resume, amendment conflict, cancellation, retry, and API restart.
- [ ] Make nodes idempotent using case, node, artifact hashes, prompt version, and code version.
- [ ] Implement a worker process backed by a leased Postgres job table; checkpoint persistence alone must not be mistaken for automatic restart scheduling. Fence stale workers and reconcile replayed node writes through idempotency keys.
- [ ] Resume review to the earliest affected stage, not always to mapping. Cancellation is an authenticated command independent of an HTTP disconnect.
- [ ] Commit `feat: orchestrate covenant case workflow`.

## Task 11: Expose authenticated APIs and AG-UI events

**Files:** create `api/routes/cases.py`, `domain/events.py`, `events/publisher.py`, `events/agui.py`; modify `main.py`; create `tests/integration/test_case_api.py` and `test_agui_events.py`.

**Produces:** REST commands and resumable AG-UI event streaming.

- [ ] Implement case create/get/run/cancel/retry, document upload, rulebook, graph, facts, calculations, evidence, review, and artifact endpoints.
- [ ] Replace the sample AG-UI graph and remove the hard-coded demo identity.
- [ ] Persist an event before publishing it and enforce unique run sequence numbers.
- [ ] Resume from the last acknowledged sequence after reconnect.
- [ ] Publish domain events only, never hidden reasoning or raw document bodies.
- [ ] Stream run, node and safe tool-call lifecycle with stable call IDs, agent role, tool name, status, timestamps, latency, redacted input/output summaries, evidence references and typed error class.
- [ ] Use AG-UI tool-call events for model-requested tools and custom envelopes for deterministic workflow nodes. Persist completion before publishing it.
- [ ] Emit `EVIDENCE_FOUND`, `DEFINITION_RESOLVED`, `CALCULATION_COMPLETED`, `REVIEW_REQUIRED`, `RESULT_INVALIDATED`, `APPROVAL_INVALIDATED` and `PACKAGE_REVISED` application events.
- [ ] Add bounded event payloads and tests proving document bodies, hidden reasoning, provider payloads and secrets never enter the client stream.
- [ ] Authenticate every command and rate-limit run creation.
- [ ] Add revision creation, impact lookup, snapshot and revision-bound decision endpoints from `docs/implementation-contract.md`. Publish custom domain events inside AG-UI envelopes and retain decimal strings over JSON.
- [ ] Commit `feat: expose covenant workflow api`.

## Task 12: Render certificates and evidence packages

**Files:** create `rendering/certificate.py`, `evidence_package.py`, `api/routes/artifacts.py`, and `tests/integration/test_certificate.py`.

**Produces:** private, immutable certificate and evidence-package versions.

- [ ] Populate the agreement’s certificate form when usable; otherwise produce a labelled internal draft schedule.
- [ ] Include case ID, agreement version, test period, calculation version, draft mark, and timestamp.
- [ ] Link clauses, facts, calculations, decisions, and hashes in the evidence manifest.
- [ ] Block finalization until officer approval exists and blocking issues are zero.
- [ ] Prove any changed source or decision creates a new artifact version.
- [ ] Distinguish internal approved draft from signed/delivered certificate. Disclose unsupported officer statements and missing certificate sections; do not label an incomplete workpaper lender-ready.
- [ ] Commit `feat: render covenant certificate package`.

## Task 13: Instrument Neatlogs safely

**Files:** create `observability/neatlogs.py`, modify `main.py`, and create `tests/unit/test_observability.py`.

**Produces:** redacted operational traces keyed by case and run IDs.

- [ ] Verify current Neatlogs Python instructions, then add and lock the SDK.
- [ ] Initialize only when enabled and configured; disabled observability must not block startup.
- [ ] Trace graph nodes, model/tool calls, retries, validation failures, latency, usage, and prompt versions.
- [ ] Do not send agreements, financial tables, tokens, or secret values.
- [ ] Prove a Neatlogs failure cannot change or fail a finance case.
- [ ] Commit `feat: instrument workflow with neatlogs`.

## Task 14: Create the gold evaluation harness

**Files:** create `data/gold/schema.json` at repository root, `apps/api/evals/run.py`, `apps/api/evals/report.py`, and `apps/api/tests/evals/test_end_to_end_gold.py`. Labels have one home in root `data/gold/`.

**Produces:** JSON and Markdown reports for extraction, grounding, calculation, state, and abstention.

- [ ] Add expert-reviewed cases for opposite agreement results, amendment threshold change, and unsupported add-back review.
- [ ] Use Aon agreement plus 10-K/XLSX for maximum-leverage definitions, four-quarter periods, pro forma adjustments, threshold steps, and certificate-reference checks.
- [ ] Use Disney for development extraction and unsupported-covenant detection only. It has already been inspected and is not a holdout; interest coverage is outside the first implemented calculation scope.
- [ ] Use Celanese exhibits as separate facilities for wrong-chain rejection and threshold extraction. Assemble the appropriate original and prior amendments before scoring precedence or a full verdict.
- [ ] Use Citizens PDF and 10-Q/XLSX for parser and financial-mapping tests, but do not treat its legal labels as gold until its direct SEC agreement source is resolved.
- [ ] Validate every raw file against `data/manifest.json` before a run and fail on checksum mismatch.
- [ ] Store reviewed answer keys separately under `data/gold/`; never modify `data/raw/`.
- [ ] Add negative cases for missed covenant, OCR decimal corruption, restricted cash, lease treatment, wrong period, and conflicting waiver.
- [ ] Split evaluation by agreement, never by pages from the same agreement.
- [ ] Measure covenant recall, rule-field accuracy, citation validity, calculation accuracy, status accuracy, amendment precedence, certificate completeness, and unsupported compliance.
- [ ] Hard fail when calculation accuracy or citation presence is below 100%, an amendment gold case fails, or unsupported compliance exceeds zero.
- [ ] Also score citation semantic support, stale-approval rejection, changed-input impact recall and selective-rerun correctness. Report sample counts and coverage; zero observed false passes is not a production guarantee.
- [ ] Commit `test: add covenant gold evaluation harness`.

## Task 15: Run the backend completion gate

**Files:** create `apps/api/README.md`; modify only files required by verified failures.

- [ ] Apply migrations from zero only to a disposable Supabase test environment and run database advisors. Do not reset any shared or cloud project to run tests.
- [ ] Run `uv sync --frozen`, Ruff, mypy, full pytest, and the gold evaluation.
- [ ] Verify authenticated upload, run, interrupt, resume, calculation, approval, rendering, and signed download.
- [ ] Restart the API while a case is paused and prove it resumes from Supabase Postgres.
- [ ] Inspect current Supabase rows and Storage artifacts for the full case lineage.
- [ ] Inspect Neatlogs and prove that raw contract text and credentials were not sent.
- [ ] Run independent Python, SQL/RLS, auth, file-intake, and prompt-injection review.
- [ ] Document exact local and deployment commands and evidence.
- [ ] Commit `docs: add verified backend runbook`.

## Dependency order

```text
0 (dataset readiness and staged labels, starts first)
1 -> 2 -> 3 -> 4
              ├-> 5 -> 6 ┐
              └-> 7 -----┴-> 8 -> 9 -> 9A -> 10 -> 11 -> 12 -> 13 -> 14 -> 15
```

Tasks 5 and 6 form the legal branch. Task 7 forms the financial branch. They may run in parallel only after Tasks 1 through 4 are green and their shared interfaces are fixed.

## Deferred backend scope

- Interest coverage and DSCR beyond reusable schemas
- Negative and incurrence covenants
- Lender waiver or acceleration decisions
- ERP posting and electronic signature
- Recurring portfolio monitoring
- A general finance-agent marketplace
- Separate vector database or distributed workers

## Acceptance gate

The product direction is fixed by `docs/implementation-contract.md`. Start Tasks 0 and 1, then use stage-level tests throughout. Real-data verdict and final demo gates remain open until source-package completeness and reviewed labels are proven. Runtime credentials and connectivity are checked during implementation.
