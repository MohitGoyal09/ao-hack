# Agent interaction flow

Status: implemented interaction contract for the hackathon demo.

## Product boundary

The LLM is the conversational planner. It reads the user's request and current
case state, chooses an allowed typed tool, explains tool results, and asks for
the next missing input. It does not calculate financial ratios, mutate trusted
facts directly, resolve a human review issue, or approve a package.

Deterministic code owns the safety-critical execution boundary: validated file
storage, immutable revisions, typed tool execution, Decimal arithmetic,
authorization, review idempotency, and revision/package-hash checks.

## Submission and processing flow

1. The user selects a supported file. The composer shows an attachment chip.
2. The user adds an optional instruction and presses Enter or Send.
3. The visible user message is appended to the conversation immediately.
4. The file is stored as an immutable document version and added to a new case
   revision. Upload alone starts no worker, calculation, or review issue.
5. The UI sends the LLM private attachment context containing the case,
   revision, document identifier, filename, and inferred document kind. This
   context is part of the model thread but hidden from the visible transcript.
6. The LLM calls `inspect_case_state` before describing progress.
   The result contains a safe checklist with present document roles, missing
   required roles, and conditional evidence categories. It excludes document
   bodies, storage paths, organization metadata, credentials, and prompts.
7. The LLM chooses whether to request another document or call
   `process_uploaded_document`. The typed tool returns `awaiting_documents`
   without starting a job unless both a credit agreement and financial statement
   are registered. Legacy fixture-run and non-persisting
   ingestion helpers are not exposed to the LLM.
8. `process_uploaded_document` queues one durable worker job. The worker emits
   persisted events for PDF reading, governing-agreement resolution, definition
   compilation, evidence mapping, and deterministic calculation.
9. Conversation tool cards and the right progress panel read the same events.
10. At `completed`, `waiting_review`, or `failed`, the UI sends a hidden
    completion notification to the same LLM thread.
11. The LLM inspects current state again and explains the ratio, comparator,
    threshold, inputs, sources, limitations, or exact missing evidence.
12. A blocker displays a structured human decision card. Processing pauses
    until a named reviewer records a decision.
13. Recalculation follows the decision. Officer approval is available only for
    a completed current revision with no blockers and the exact package hash.

## Conversation history

- Every case uses the stable CopilotKit thread ID `covenant-{case_id}`.
- The AG-UI/LangGraph checkpointer retains model-visible thread messages.
- The visible transcript mirrors user, assistant, and tool messages.
- A submitted attachment instruction appears before upload finishes.
- Private attachment and completion context stays in the model thread but is
  filtered from the visible transcript.
- Upload failures preserve the visible user message, attachment, and error so
  the user can retry without losing intent.
- Optimistic attachment messages are merged with restored CopilotKit history
  until the corresponding server-backed user message arrives.

## Observability

- Durable domain events are the source of truth for the UI and replay.
- Neatlogs is optional and disabled unless `NEATLOGS_ENABLED=true` and an API
  key are configured.
- Current Neatlogs instrumentation is redacted: it excludes prompts, document
  bodies, financial facts, tokens, and evidence excerpts.
- It currently covers the legacy deterministic run span, not complete LLM,
  tool-selection, worker-phase, or conversation tracing. Do not claim full
  agent observability until those redacted spans are added and verified in the
  Neatlogs dashboard.

## Evidence behavior

- A credit agreement alone cannot produce a calculation.
- Bundled financial fixtures are never substituted silently.
- The agent requests financial statements for the applicable test period.
- Amendments, adjustment support, waivers, and certificate forms are requested
  only when the case or extracted terms require them.

## Judge demo

1. Create a private case.
2. Attach the credit agreement and ask the agent to review it.
3. Show the agent inspecting state and requesting period-matched financials.
4. Attach the financial statement and ask the agent to continue.
5. Show the processing tool and synchronized stage events.
6. Show the deterministic calculation and the agent explanation.
7. Resolve any human-review interrupt.
8. Show recalculation, exact officer approval, and the draft package.

Do not add artificial delays. Progressive UI is driven by real tool and durable
worker events.

## Institutional workspace presentation

- The desktop screen has a case rail, central conversation record, and persistent
  context rail. The centre uses two columns only for comparable evidence such as
  documents, calculation values, and input amounts.
- User prompts appear immediately. LLM calls and durable worker stages appear as
  named cards with queued, running, complete, blocked, or failed states.
- The progress rail links to the corresponding conversation record. Completed
  steps are green and struck through; active work is blue and animated; review
  blocks are amber; failures are red; pending and stale work is gray.
- Document cards show the safe title, role, version, size, and short hash. Opening
  a card uses an authorized blob request and an in-app preview; raw storage paths
  are never exposed.
- Calculation cards show the ratio, contractual comparator and threshold, typed
  inputs, citations, headroom, and period check. A period mismatch is labelled as
  review-required even when the raw arithmetic falls inside the threshold.
