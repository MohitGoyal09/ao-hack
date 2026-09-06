# Covenant Certificate Demo: A to Z

Last updated: 2026-09-06. This is the canonical handoff for a new agent
session. Read this file first, then `AGENTS.md`,
`docs/implementation-contract.md`, and `docs/agent-interaction-flow.md`.
Current code wins when a document is stale.

## Product and authority boundary

Covenant Certificate is a borrower-side treasury assistant. It gathers the
governing loan documents and period-matched financial evidence, extracts the
covenant definition, maps evidence, runs exact arithmetic, pauses for human
judgment, and prepares an officer-reviewed draft package. It is not legal
advice, an e-signature, a signed certificate, or lender delivery.

The LLM is the planner and conversational decision-maker. It reads the user
request, conversation history, current case state, and tool results. It decides
which allowed tool to call and what question to ask next.

Deterministic code is limited to validated file storage and parsing, typed tool
input/output, Decimal arithmetic, authorization, organization membership,
immutable revisions and hashes, job idempotency, and human approval gates. The
LLM must never invent a clause, amount, formula, source, status, or verdict. It
must never resolve a review issue or approve a package.

## Document checklist

On the first inspection, the agent gives one complete checklist.

Always required:

1. Governing credit agreement.
2. Financial statement matched to the covenant test period.

Conditional, requested only when relevant:

1. Applicable amendments.
2. Debt and unrestricted-cash schedules.
3. Support for adjustments or EBITDA add-backs.
4. Waiver or consent letters.
5. Required certificate form.

An agreement alone must not start the worker. The typed processing tool checks
that both required roles exist. When they do not, it returns
`awaiting_documents` so the LLM can ask for evidence without failing the chat.

## LangGraph and durable pipeline

```text
User prompt + attachment
        |
        v
Store immutable document -> new revision -> DOCUMENT_UPLOADED
        |
        v
LangGraph LLM planner (same case thread)
        |
        +-> inspect_case_state
        |       |
        |       +-> missing docs -> explain full checklist -> wait
        |       |
        |       +-> required docs present
        |               |
        +---------------+
        |
        v
process_uploaded_document (typed tool)
        |
        v
durable worker job
        |
        +-> DOCUMENT_READ
        +-> AGREEMENT_RESOLVED
        +-> DEFINITIONS_COMPILED
        +-> EVIDENCE_MAPPED
        +-> CALCULATION_STARTED
        +-> CALCULATION_COMPLETED
        |
        +-> unclear evidence -> REVIEW_REQUIRED -> human decision
        |                                      |
        |                                      +-> recorded rationale
        |                                      +-> recalculation
        |
        +-> valid result -> RUN_COMPLETED -> draft package
                                               |
                                               +-> officer approval binds exact
                                                   revision, inputs, and hash
```

One durable worker may run several mechanical phases for the hackathon. The LLM
decides whether to start it. Durable events, not timers, drive both tool cards
and the right progress rail.

## Conversation history

- Each case uses `covenant-{case_id}` as its stable thread ID.
- The AG-UI/LangGraph checkpointer retains model-visible messages.
- The visible transcript mirrors user, assistant, and tool messages.
- The user prompt appears as soon as Enter is pressed.
- Attachment and completion metadata are private model context and are hidden
  from the transcript.
- At `completed`, `waiting_review`, or `failed`, the UI sends a hidden
  completion notice. The LLM inspects state and explains the result or blocker.
- Memory mode loses model history when the API restarts. Hosted checkpoint
  persistence is required for restart-safe conversations.

## UI contract

The desktop workspace has three zones: case navigation on the left, the
conversation and work record in the centre, and synchronized context on the
right. Comparable evidence uses two columns and collapses to one when space is
narrow. The long-form workpaper must not be dumped into chat.

Status system:

- pending: gray;
- running: blue with a reduced-motion-safe spinner;
- complete: green with a struck-through step label;
- blocked/review: amber;
- failed: red;
- stale/superseded: muted gray.

Tool cards show a readable name, purpose, input, output, and state. Raw JSON is
optional. Assistant replies support copy, Markdown download, and feedback.

Document cards show title, role, version, size, and short hash. A click opens an
authorized preview. Preview responses use `private, no-store`, `nosniff`, CSP
sandboxing, and an iframe sandbox. Metadata never returns document bodies or
storage paths.

Calculation cards show the ratio, comparator, threshold, typed inputs, sources,
headroom or breach distance, period check, and plain-language result. A period
mismatch is review-required even when raw arithmetic is inside the threshold.

## Judge demo script

Use a fresh private case. Do not reuse a case with old events.

1. Open `http://localhost:3000`.
2. Create **Aurora: net leverage passes**. Confirm all seven steps are pending.
3. Attach `data/raw/pdf-fixtures/aon-credit-agreement.pdf`.
4. Send: `Review this agreement and tell me every other document you need before calculating the covenant.`
5. Show the user prompt, `Inspect case readiness` card, document card, PDF
   preview, and step 1 becoming complete.
6. Confirm the agent asks for period-matched financials plus conditional items.
   No worker should start yet.
7. Attach a financial statement. The existing extraction fixture is
   `data/raw/sec/aon/2023-form-10k.html`.
8. Send: `Continue the review and explain the result or any evidence mismatch.`
9. Show the agent-selected process tool, worker stage cards, and synced rail.
10. Show the calculation and the agent explanation.
11. The 2023 source does not match a later test date. Treat it as
    `NEEDS_REVIEW`, never a compliance pass.
12. Show the human review card and explain that processing pauses for a named
    reviewer and recorded rationale.
13. With a controlled period-matched fixture, resolve review, recalculate,
    approve the exact current revision as an officer, and download the draft.

## Verified evidence

Verified on 2026-09-06:

- `uv run python -m unittest discover -s tests`: 172 passed, 13 expected skips.
- `npm run build`: Next.js production build and TypeScript passed.
- `git diff --check` passed before this documentation update.
- Internal browser: fresh case starts pending; attachment chip appears; Enter
  submits; the prompt stays visible; document metadata appears in both columns;
  PDF preview opens; agreement-only intake stays pending; the LLM asks for the
  financial statement and conditional documents.

One live LLM turn returned `Service temporarily overloaded`; a retry succeeded.
This is a provider availability boundary, not deterministic fallback proof.

## Observability

Durable case events are the product source of truth. Neatlogs is optional and
requires `NEATLOGS_ENABLED=true` plus its API key. Redaction excludes prompts,
document bodies, financial facts, tokens, and evidence excerpts.

Honest current claim: Neatlogs covers the legacy deterministic run span. It does
not yet trace full AG-UI turns, tool selection, worker phases, or completion
callbacks. Do not claim full agent observability until those spans are added and
verified in its dashboard.

## Open issues from the Terra review

### Critical: AG-UI authorization

`/ag-ui` is mounted without a route dependency. Agent tools can inspect a case
or enqueue work without binding the authenticated principal to tool execution.
Before hosted or multi-tenant release, authenticate each AG-UI request, put the
principal and organization in LangGraph run context, enforce case membership in
both tools, and add outsider tests. This is the top unresolved security issue.

### High: ambiguous document roles

The UI still infers roles from filename tokens. It recognizes `financial`,
`statement`, `10-k`, `10k`, and `annual-report`, but `Q1.pdf` can still be
misclassified. Final design: store ambiguous files as `unclassified`, extract
safe metadata/text, and let the LLM call a narrow typed classification tool. Do
not restore a required document-type selector.

### Medium: metadata refresh

Metadata refresh is keyed mainly by document IDs. Reusing a document ID for a
new version can show stale version/hash text until revision/event sequence is
added to the refresh key.

### Medium: preview keyboard behavior

The preview is labelled and sandboxed but still needs initial focus, Escape,
focus trapping, and focus restoration.

### Provider availability

The real LLM can be overloaded. Add a friendly retry card and provider
retry/fallback policy without replacing the LLM planner with a script.

## Issues fixed in this workstream

- Fresh cases no longer start with step 1 complete.
- Upload alone no longer starts work or creates review issues.
- Enter sends the prompt; the attachment and user message stay visible.
- Markdown, tables, copy/download, and named tool cards render correctly.
- Sidebar states derive from persisted snapshots and events.
- Outputs and Context no longer show meaningless status badges.
- UUID-only documents became readable metadata cards with preview.
- Definition and evidence cards give completed stages permanent anchors.
- Calculation output explains the result and period mismatch.
- Agreement-only processing returns `awaiting_documents` instead of running.
- `10K` and `10-K` financial filenames are recognized.
- HTML previews are sandboxed and security headers pass through the proxy.

## Main files

- `apps/api/src/agent.py`: LLM prompt, tools, checklist, process guard.
- `apps/api/src/covenant/pipeline.py`: worker stages and evidence logic.
- `apps/api/main.py`: case/document routes, preview, AG-UI mount.
- `apps/web/src/components/workspace/CopilotComposer.tsx`: chat and uploads.
- `apps/web/src/components/workspace/Conversation.tsx`: main work record.
- `apps/web/src/components/workspace/ContextRail.tsx`: synchronized stages.
- `apps/web/src/lib/workflow.ts`: pure stage derivation.
- `apps/web/src/components/workspace/DocumentPreview.tsx`: safe preview.
- `docs/agent-interaction-flow.md`: interaction contract.

## Run commands

```bash
cd apps/api
DATABASE_URL= SUPABASE_DB_URL= SUPABASE_URL= SUPABASE_SECRET_KEY= \
  uv run uvicorn main:app --host 127.0.0.1 --port 8123

cd apps/web
npm run dev

cd apps/api && uv run python -m unittest discover -s tests
cd apps/web && npm run build
git diff --check
```

`LITELLM_API_KEY=` disables the live provider for tests. Never use an offline
scripted reply as evidence that the real LLM reasoned over a document.

## Next-agent order

1. Fix AG-UI authentication and membership enforcement.
2. Replace filename-only classification with agent-selected typed
   classification for ambiguous files.
3. Add friendly provider retry UX.
4. Complete keyboard-modal behavior and metadata version refresh.
5. Re-run the two-document internal-browser flow.
6. Capture calculation/review proof and record the exact tested boundary.
7. Only then claim the full A-to-Z demo is release-ready.

Do not split the demo worker into many services. One durable job with real stage
events is enough. Keep the LLM as planner and the deterministic boundary narrow.
