# Teammate handoff: Covenant Certificate

Last verified: 2026-09-05 against commit `b7fefd7`, before this document update.

This is the main start file for a new engineer or coding agent. It replaces the
earlier chat as execution context. Current code always wins if it conflicts with
this file.

## Copy this prompt into the new agent

```text
Work in this repository as the implementation owner for Covenant Certificate.
Read docs/agent-handoff.md completely, then docs/implementation-contract.md.
Inspect the current branch and code before changing anything because this
handoff can become stale. Follow its phase order. Build the production pipeline
first; demo polish is later.

For each phase, write a failing test first, implement the smallest correct slice,
run the full backend suite and frontend production build, review the diff, update
the handoff, then commit. Never expose secrets or make the model authoritative
for calculations, legal conclusions, review decisions, or officer approval.
Never call a result a signed certificate or full agreement compliance.

Start with Phase 1. Before editing, report the current commit, dirty files,
detected test/build commands, Phase 1 scope, and Phase 1 non-goals.
```

## Product in simple language

A finance team uploads a loan agreement, amendments, and financial records. The
system finds the applicable covenant terms, maps each number to source evidence,
and calculates the supported ratio with normal Python code. If a clause or fact
is unclear, it stops and asks a person. An authorized officer can approve only
the exact current draft package.

The hard part is the contract definition, not the division. The same financial
numbers can produce a different result under another agreement because each
agreement defines debt, EBITDA, adjustments, periods, and thresholds differently.

## Non-negotiable scope and safety

- Build one strong workflow first: maximum gross or net leverage.
- Inventory other obligations, but mark unsupported ones clearly.
- Backend owns decisions. Frontend displays state and sends commands.
- LLMs propose interpretations and call tools. They never do final arithmetic,
  alter authoritative data, accept evidence, approve, or sign.
- Use typed Python and `Decimal` for calculations. JSON money is a string.
- Missing or unclear evidence never becomes zero and never becomes a pass.
- A leverage pass is not full agreement compliance.
- Interpretation, evidence acceptance, correction, and officer approval are
  separate human actions with identity, role, reason, revision, and time.
- Internal approval freezes a reviewed draft. It is not an electronic signature.
- Aon sources are extraction fixtures. Their period mismatch means they do not
  prove a real Aon compliance result.
- Keep keys in secrets. Never commit `.env`.
- AO is a development tool only, not a runtime dependency.

## Read order

1. `docs/agent-handoff.md` — this execution packet.
2. `docs/implementation-contract.md` — controlling product contract.
3. `docs/covenant-certificate-backend-architecture.md` — target design.
4. `docs/covenant-certificate-domain-and-build-research.md` — domain research.
5. `docs/covenant-compliance-primary-sources.md` — control research.
6. `docs/superpowers/plans/2026-09-04-covenant-certificate-backend.md`.
7. `docs/superpowers/plans/2026-09-05-covenant-certificate-frontend.md`.
8. `data/README.md` and `data/case-readiness.json`.

The implementation contract overrules the older plans. Current source overrules
all documentation status.

## Repository map

| Path | Responsibility |
|---|---|
| `apps/api/main.py` | FastAPI routes, auth dependency, AG-UI route |
| `apps/api/src/agent.py` | LangGraph agent and its tools |
| `apps/api/src/covenant/` | Domain, parsing, calculation, review, revisions, audit |
| `apps/api/src/platform/` | Supabase, job queue, checkpoints, Neatlogs |
| `apps/api/supabase/` | Local config and forward SQL migrations |
| `apps/api/litellm/` | LiteLLM Gemini gateway |
| `apps/web/` | Next.js and CopilotKit frontend |
| `data/raw/` | Original source files |
| `data/annotations/` | Proposed labels |
| `data/gold/` | Reviewed extraction-only labels |
| `references/` | Read-only upstream references |

Do not build inside `references/`. Copy only needed patterns into the apps and
retain their license.

## Current verified status

Fresh checks on 2026-09-05:

| Area | Status |
|---|---|
| Git | local `main` and `origin/main` were equal: `0 0` |
| Backend tests | 39 of 39 passed |
| Frontend | `npm ci` and production build passed |
| Dependency audit | npm reported 19 issues: 6 low, 6 moderate, 7 high |
| Supabase project | `ao-hack`, `ap-south-1`, active and linked |
| Hosted migrations | all 4 local migrations match hosted history |
| Database lint | local and hosted lint returned no schema errors |
| Production readiness | not ready; real infrastructure E2E is missing |

Run the baseline again instead of trusting these counts:

```bash
git status --short --branch
git fetch origin
git rev-list --left-right --count main...origin/main

cd apps/api
uv sync --frozen
uv run python -m unittest discover -s tests -v

cd ../web
npm ci
npm run build
```

If the uv home cache is blocked:

```bash
UV_CACHE_DIR=/tmp/uv-cache-ao uv sync --frozen
```

## What is implemented

### Covenant core

- Typed domain objects and exact decimal serialization.
- Deterministic ratio calculation with no `eval` or model-written code.
- Fail-closed policy for missing facts, unclear precedence, missing proof, and
  incomplete reviewer identity or rationale.
- Supported leverage is evaluated; unsupported obligations stay visible.
- Evidence manifest, content hashes, hash-chained trace, and draft package.
- Real nine-node covenant LangGraph plus a sequential test fallback.
- Five curated cases, including one built from real Aon source extraction.

### PDF and financial extraction

- `pdfplumber` extracts the Aon leverage clause, definition, and three threshold
  tiers from one known agreement PDF.
- Fixed regular expressions extract selected facts from the local Aon 10-K HTML.
- File hashes, source pages/sections, locators, and excerpts are returned.
- EBITDA and debt are labelled proxies.
- This is not a general parser. It does not handle arbitrary uploads, scans/OCR,
  full cross-reference chains, arbitrary amendments, or chosen reporting periods.

### Agent and tools

The model-backed agent has four tools:

1. `list_covenant_cases`.
2. `run_covenant_case`.
3. `ingest_covenant_document`.
4. `reevaluate_covenant_case`.

It is exposed at `/ag-ui`. Without credentials, an offline deterministic graph
handles basic case requests.

Important limitation: ingest accepts a server file path, parses only the Aon
shape, does not persist the source, and does not create a revision. Re-evaluate
does not consume newly extracted state. These are helper tools, not the complete
production agent workflow.

### Human review and change handling

- Revision, impact, review resolution, snapshot, and officer approval APIs exist.
- Stale review commands and idempotency conflicts return HTTP 409.
- Approval checks the exact current ratio, threshold, comparator, inputs,
  revision, and package hash.
- A later revision supersedes an old approval.
- This logic is tested but held in process memory.

### Infrastructure

- Supabase Auth validation and run artifact persistence adapters exist.
- The hosted `ao-hack` Supabase project exists in `ap-south-1`.
- Four applied migrations create 17 tenant-scoped workflow tables, the private
  bucket, RLS policies, explicit Data API grants, and the durable job queue.
- The fourth migration removes legacy user-folder Storage access, binds child
  rows to same-tenant parents, narrows grants, validates approval hashes/numbers,
  adds FK indexes, and protects append-only evidence and decision records.
- The production schema now covers organizations, memberships, cases, immutable
  document versions, revisions, document bundles, changes, impacts, rules,
  financial facts, review issues/decisions, artifacts, approvals, and events.
- Memory and Postgres job stores implement lease, retry, heartbeat, cancellation,
  and stale-worker fencing.
- LangGraph has Postgres checkpoint code and an in-memory fallback.
- LiteLLM aliases route `covenant-fast` and `covenant-strong` to Gemini.
- Neatlogs is optional and designed to receive identifiers, not raw documents.

### Frontend and data

- Current Next.js page lists cases, runs REST calculations, and shows results,
  evidence, clauses, traces, reviewer controls, and CopilotKit chat.
- Ten reviewed `data/gold/` labels contain source spans and reviewer metadata.
- Gold labels test extraction only. They do not claim a compliance verdict.

## Main gaps and bugs

| Priority | Gap | Consequence |
|---|---|---|
| P0 | Global in-memory `RevisionStore` | restart loses revisions, issues, events, idempotency, approvals |
| P0 | Revision/review/approval routes lack auth | body-supplied actor and role are not a real authority boundary |
| P0 | Queue is not wired to API execution | runs execute inline; no worker consumes durable jobs |
| P0 | Postgres/checkpoint packages are absent from `pyproject.toml` | configured durability can silently fall back to memory |
| P0 | Configured durability catches broad errors | a broken database can look like a working offline system |
| P0 | No upload API or immutable intake transaction | agent accepts unsafe server paths and bypasses Storage/versioning |
| P0 | Extracted data is not authoritative revision state | upload, review, and recalculation are not one E2E flow |
| P1 | No durable event outbox and replay | reconnect cannot restore exact progress |
| P1 | AG-UI route exists but custom domain events do not | UI cannot show real node/tool/review progress |
| P1 | No durable LangGraph interrupt/resume review | human review is REST state, not a paused agent execution |
| P1 | Parser supports one Aon pattern | arbitrary agreements and amendment chains do not work |
| P1 | No real Gemini/LiteLLM proof | tool calls, structured output, retries, cost data unverified |
| P1 | Schema is hosted but backend repositories are not wired to it | hosted RLS, persistence, Storage, queue, and restart behavior are not yet E2E proven |
| P1 | Frontend misses intake, revisions, event replay, full review inbox | production workflow cannot be completed in UI |
| P2 | No untouched agreement family or final calculation labels | product accuracy is not measured |
| P2 | No PDF workpaper export | certificate is a JSON draft object |
| P2 | npm audit has 19 findings | must be triaged before a security claim |

## Target production flow

```text
Authenticated upload
  -> immutable private object + SHA-256
  -> document version + case revision
  -> durable job
  -> borrower/facility/agreement/amendment/period resolution
  -> covenant inventory + cited definition graph
  -> proposed facts and mappings
  -> durable human review pause when unclear
  -> deterministic Decimal calculation
  -> policy and coverage check
  -> persisted result, evidence, trace, package, and events
  -> live AG-UI updates with reconnect and replay
  -> officer approves exact current draft
  -> marked draft or incomplete workpaper export
```

Every step must retry safely. Browser disconnect does not cancel work. A stale
worker, reviewer command, or approval cannot publish.

## Required implementation order

Do not start demo polish until Phases 1 through 6 have acceptance proof.

### Phase 0 — Reconfirm baseline

- Fetch and read any new commits.
- Run backend tests and frontend build.
- Record fresh counts and dirty files.

Done when: there is no hidden merge, dependency, or baseline failure.

### Phase 1 — Make persistence explicit and fail safe

Owner: `apps/api/pyproject.toml`, `apps/api/src/platform/`, migrations, tests.

- Add and lock Postgres and LangGraph Postgres-checkpoint packages.
- Configured production mode must fail readiness if DB setup fails.
- Memory fallback is allowed only when no database URL is configured.
- Add readiness that reports configured and verified stores.
- Add a real Postgres queue/checkpoint integration test.
- Fix the `.env.example` whitespace bug and document DB URL types.

Done when: bad configured DB fails readiness, offline mode is explicit, and real
Postgres queue state survives process restart.

### Phase 2 — Persist revisions and enforce authority

Owner: revision repository, API auth, new forward migration, integration tests.

- Add repository interfaces with Postgres and explicit memory implementations.
- Persist revisions, changes, impacts, issues, idempotency, approvals, snapshots,
  and domain events.
- Authenticate every private read and mutation.
- Derive organization, actor, and role from verified identity, never request JSON.
- Enforce tenant ownership and reviewer/officer roles in API and RLS.
- Make invalidation, issue resolution, events, and approval transactional.

Done when: data survives restart, cross-tenant access fails, 409 semantics survive
restart, and body actor/role cannot raise privilege.

### Phase 3 — Build immutable document intake

Owner: document API/service, Storage adapter, parser interfaces, tests.

- Add limited multipart uploads for agreement, amendment, financial statement,
  support, and certificate-form types.
- Validate size/type, calculate SHA-256 while streaming, and use tenant paths.
- Persist uploader, hash, media type, role, borrower/facility, dates, and period.
- Replacement creates a new immutable version.
- Create one case revision, durable event, and queued job.
- Change the agent tool to accept document ID, not a filesystem path.
- Return explicit OCR-required or unsupported states.

Done when: one authenticated upload creates one immutable object, document
version, case revision, queued job, and durable event.

### Phase 4 — Connect the queue to the covenant workflow

Owner: worker entry point, queue calls, orchestrator, case repository, recovery.

- Lease, heartbeat, run, retry transient failure, and fence final publication.
- Build cases from persisted documents, reviewed rules, and facts.
- Connect extraction to `CaseRevision`, `ChangeSet`, and `ImpactSet`.
- Re-run precedence and covenant inventory after amendments.
- Persist calculation, coverage, evidence, trace, and package.
- Make cancellation explicit and authenticated.

Done when: upload-to-worker-to-snapshot works on Supabase; restart recovers; an
old worker cannot publish; old approvals cannot authorize a new revision.

### Phase 5 — Complete tools and durable human review

Owner: `agent.py`, LangGraph state, tool schemas, LiteLLM/Gemini tests.

Target tools:

1. Open cases and current revision.
2. Register uploaded document ID.
3. Resolve agreement and amendment chain.
4. Inventory supported and unsupported covenants.
5. Propose cited definitions and financial facts.
6. Request human review with required evidence and expected impact.
7. Resume the exact paused run after server-authorized review.
8. Run deterministic calculation.
9. Explain persisted results and citations.
10. Prepare a draft package for officer review.

- Use typed schemas and artifact IDs. No raw DB or filesystem tool.
- Add durable LangGraph checkpoints and real `interrupt`/resume review gates.
- Record aliases, resolved model, prompt version, call IDs, hashes, latency,
  retries, tokens, and cost without raw source text.
- Use Gemini Flash for extraction/classification and Pro for hard interpretation.
- Keep calculation and policy outside the model.

Done when: a real Gemini run calls tools, pauses, survives restart, resumes only
with the matching decision, and matches direct deterministic calculation.

### Phase 6 — Add durable AG-UI events and replay

Owner: event outbox, AG-UI adapter, snapshot/replay tests.

- Persist run, node, tool, evidence, review, impact, invalidation, recalculation,
  approval invalidation, package revision, completion, and failure events.
- Use standard AG-UI events and custom envelopes for product events.
- Store case/revision/run IDs, monotonic sequence, redacted summary, artifacts.
- Commit state plus event atomically.
- Add snapshot plus replay after a sequence, heartbeat, backpressure, redaction.

Done when: disconnect and reconnect loads a snapshot, replays each missed event
once in order, and reaches the same final state.

### Phase 7 — Complete the frontend workflow

Owner: `apps/web/`. Start after backend contracts are stable.

- Add Supabase sign-in and secure server-side token forwarding.
- Add case creation and document intake.
- Show live pipeline, tool calls, evidence, definitions, formula, coverage,
  blockers, and errors from real backend events.
- Add review inbox with rationale, evidence, role checks, and stale handling.
- Show old/new revisions, impact, invalidation, and recalculation.
- Show exact locked approval values.
- Add loading, empty, error, reconnect, offline, and permission states.

Done when: a reviewer can complete upload through exact draft approval in the UI.
Test desktop, 375 px, keyboard-only, and a screen-reader smoke path.

### Phase 8 — Build the accuracy harness

Owner: `data/`, eval scripts, CI.

- Add reviewed labels for definitions, thresholds, periods, precedence, mapping,
  calculations, unsupported detection, and refusal/review behavior.
- Keep source hash, spans, reviewer, date, scope, and rationale.
- Split by issuer/facility/agreement family.
- Acquire one untouched agreement family for holdout.
- Measure extraction, span/citation validity, calculation match, unsupported
  recall, review behavior, and false passes.
- Set thresholds before tuning. Report counts with denominators.

Done when: deterministic gates run in CI and a controlled model-eval job reports
versioned metrics without tuning on holdout.

### Phase 9 — Export, security, operations, deployment

- Render a marked draft/incomplete PDF with citations, assumptions, exclusions,
  approvals, hashes, and unsigned statements.
- Add limits, headers, secret scanning, dependency triage, backups, retention,
  deletion policy, and safe errors.
- Prove RLS, tenant isolation, private downloads, and audit retention.
- Add readiness, queue, stuck-job, failure, cost, and review-wait metrics.
- Deploy web, API, worker, LiteLLM, Supabase, and Neatlogs with separate secrets.
- Test migration, rollback, restart recovery, and browser E2E in staging.

Done when: staging passes the real full path and deploy/rollback/recovery runbooks.

### Phase 10 — Demo polish

Use one honest scenario: upload, watch live extraction, stop for evidence review,
resolve it, add an amendment/correction, show invalidation and revision diff,
recalculate, then approve the exact new draft. Keep the two-agreement comparison
as a labelled hypothetical, not a real issuer finding.

## API contract to finish

Use typed request/response models, not raw `dict` bodies:

```text
POST /api/cases
POST /api/cases/{case_id}/documents
GET  /api/documents/{document_id}
POST /api/cases/{case_id}/revisions
POST /api/cases/{case_id}/runs
GET  /api/runs/{run_id}
POST /api/runs/{run_id}/cancel
GET  /api/cases/{case_id}/snapshot
GET  /api/cases/{case_id}/events?after_sequence=N
POST /api/review-issues/{issue_id}/resolve
POST /api/cases/{case_id}/officer-approval
GET  /api/packages/{package_id}
GET  /api/packages/{package_id}/download
POST /ag-ui
```

Private reads and mutations need organization membership. Review needs reviewer
authority. Approval needs officer authority. Identity always comes from server.

## Suggested three-person split

| Person | Primary work | Shared contract |
|---|---|---|
| Backend/data | Phases 1–4 | API schemas and event records |
| Agent/eval | Phases 5, 6, 8 | review schema and frontend event contract |
| Frontend/product | Phase 7, then demo | snapshot, events, review, approval |

Land Phases 1 and 2 before broad parallel work. Keep file ownership separate.
Never let two people edit the same migration, API model, or event schema at once.

## Human inputs the agent cannot invent

- Supabase URL, server secret, DB URLs, and reviewer/officer role claims.
- Gemini key and LiteLLM keys.
- Neatlogs project settings if enabled.
- A finance/domain reviewer for interpretation and gold-label approval.
- One untouched agreement family with compatible financials.
- Deployment accounts and approval before shared migrations.

Without these, use local containers and fake identity fixtures. Mark live
acceptance blocked. Do not claim it passed.

## Test matrix before completion

| Level | Required proof |
|---|---|
| Unit | calculation, policy, hashes, parsing, impact, auth, event mapping |
| Repository | real Postgres transactions, idempotency, RLS, restart |
| Storage | upload, hash, immutability, isolation, private read |
| Worker | lease, heartbeat, retry, fencing, cancellation, crash recovery |
| Agent | Gemini tool calls, refusal, interrupt/resume, calculation parity |
| Stream | ordered events, reconnect, replay, redaction, backpressure |
| API | authenticated full flow and stale conflicts |
| Browser | upload through approval on desktop and 375 px |
| Evaluation | reviewed labels, family split, holdout, false-pass count |
| Deployment | migration, readiness, rollback, restart, smoke path |

Memory-only unit tests do not prove Supabase, recovery, Gemini, event replay,
browser behavior, or deployment.

## Definition of complete

- Authenticated case creation and private uploads work.
- Sources are immutable, hashed, versioned, and tenant-isolated.
- Agreement chain and supported scope are explicit.
- Each used rule and fact has a valid source.
- Unclear evidence creates a durable human pause.
- Matching authorized review resumes the correct run after restart.
- Exact deterministic calculation passes golden tests.
- New revision invalidates affected outputs and approvals.
- Jobs/checkpoints recover without duplicate publish.
- Frontend shows live work and reconnects with snapshot plus replay.
- Approval binds exact current values and package hash.
- Export is a marked draft/incomplete workpaper, never a fake signature.
- Supabase, Gemini through LiteLLM, Neatlogs, API, worker, and web have staging proof.
- Tests, builds, security checks, and eval gates pass with fresh evidence.
- Documentation matches final code and has no known false claims.

## Commit and push discipline

- Never reset, force-push, or rewrite teammate work.
- Use one focused commit per green phase. No AI co-author trailer.
- Before push: backend tests, frontend build, `git diff --check`, full diff review.
- If remote moved, fetch and rebase only after checking dirty files. Resolve by
  understanding both changes, rerun all checks, then normal push.
- Update this file after each phase with commit, checks, completed work, remaining
  gaps, migrations, and live-integration limits.

## First action

Start Phase 1. The hosted schema is ready. Postgres queue/checkpoint code exists,
but its runtime packages are not declared and configured failures can silently
fall back to memory. Fix and test that, then wire the backend repositories to the
new Supabase tables.
