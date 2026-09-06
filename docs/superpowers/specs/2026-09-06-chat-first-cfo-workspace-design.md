# Chat-first CFO workspace design

Status: approved direction. This specification controls the frontend redesign.

## Product goal

Replace the current landing-page and stacked-dashboard experience with a focused finance-agent workspace. A controller should be able to open a case, give the agent documents or instructions, watch the covenant workflow advance, resolve genuine judgment calls, and inspect every resulting artifact without leaving one screen.

The interface must feel like a professional Office of the CFO workbench, not a marketing page, generic chatbot, developer IDE, or collection of forms.

## Chosen direction

Use a hybrid inspired by conversation-first agent products:

- 70% conversation and artifact structure: readable messages, inline results, persistent files and outputs.
- 20% operational navigation: compact case list, active case title, clear running and blocked state.
- 10% covenant-specific controls: definition citations, evidence mappings, deterministic calculation, revision history, review decisions, and officer approval.

Do not copy another product's branding or chrome. Transfer the interaction model and build a distinct institutional finance visual system.

## Desktop layout

The application uses one full-height shell:

```text
┌──────────────┬──────────────────────────────────┬────────────────────────┐
│ Case rail    │ Conversation and active work     │ Case context           │
│              │                                  │                        │
│ New case     │ User message or document upload  │ Workflow               │
│ Recent cases │ Agent stage and tool cards       │ Evidence               │
│ Review inbox │ Clause and evidence cards        │ Artifacts              │
│              │ Calculation and result cards     │                        │
│              │ Human decision interrupt         │ Current revision       │
│              │                                  │ Coverage and blockers  │
│              │ Fixed composer                    │ Draft package          │
└──────────────┴──────────────────────────────────┴────────────────────────┘
```

- Left rail: 240-280 px, collapsible. It owns case search, new-case creation, recent cases, status badges, and review-inbox count.
- Main conversation: flexible width with a readable maximum content width. It owns user intent, real agent activity, domain results, interrupts, and next actions.
- Right context rail: 320-380 px, collapsible. It has Workflow, Evidence, and Artifacts tabs. It never repeats the full conversation.
- Composer: fixed to the bottom of the main area. It supports a message, document attachment, case-aware suggestions, and send/cancel state.

The root route opens this workspace directly. Remove the large hero, marketing sections, curated-card grid, and separate chat showcase. An empty workspace introduces the product in two short sentences and offers prepared cases as compact starter actions.

## Supported viewport

This is a desktop-first Office of the CFO application. The supported product
width is 1024 px and above, optimized for 1440 px. Mobile and phone layouts are
out of scope for the hackathon because the workflow depends on simultaneous
conversation, evidence, calculation, and review context.

At narrower widths, show a clear “Open on a desktop” message instead of
compressing finance tables and approval controls into an unsafe layout. Long
hashes, clauses, and filenames must still wrap or truncate with an explicit
reveal action at supported widths.

## Step-by-step workflow

The right workflow tab shows seven ordered stages:

1. Documents received
2. Governing agreement resolved
3. Covenant definitions compiled
4. Financial evidence mapped
5. Ratio calculated
6. Controller review
7. Draft package prepared

Each stage has exactly one state: pending, running, blocked, complete, failed, or stale. Progress comes from persisted backend state and events, never a timer. Selecting a stage scrolls the conversation to its latest card and filters related evidence.

The interface must show why a stage is blocked and the single best next action. A completed stage may become stale after a new document or amendment; it must not remain green.

## Conversation model

The conversation is a structured timeline, not plain prose. It can contain:

- User messages and uploaded-document cards.
- Agent stage cards with role, action, state, duration, and safe summary.
- Expandable tool-call cards linked to evidence or artifacts.
- Clause cards with document, section, page, excerpt, and governing status.
- Evidence-mapping cards with fact, period, entity, units, source, and support state.
- Deterministic calculation cards with formula, inputs, intermediates, threshold, result, and headroom.
- Review-interrupt cards with the question, source context, alternatives, impact, required rationale, and evidence selector.
- Revision-diff cards showing changed inputs and invalidated results or approvals.
- Draft-package cards with scope, limitations, revision, hash, approval state, preview, and download.

The chat model may explain or propose. It must not authorize evidence, change authoritative facts, perform arithmetic, resolve review issues, or approve a package. Those actions use structured server-authorized controls.

## Right context rail

### Workflow

Shows the seven stages, current run, connection state, last durable event, and any blocker. It is the primary progress view.

### Evidence

Shows the governing document chain, cited definitions, financial sources, evidence gaps, and active source preview. Clicking an inline citation selects the same source here.

### Artifacts

Shows only generated or uploaded outputs relevant to the current revision: original documents, extracted rulebook, calculation schedule, review record, revision comparison, evidence manifest, and draft certificate. Stale and superseded artifacts remain visible but clearly marked.

## Human-review safety contract

The current implementation has a release-blocking contradiction: resolving an issue can mark a package ready and allow officer approval while the run remains `waiting_review`, the visible result remains `NEEDS_REVIEW`, and the certificate says finalization is not allowed.

Required behavior:

1. A review decision is submitted with issue ID, revision ID, expected bundle hash, decision kind, rationale, evidence references, and idempotency key.
2. The server validates identity, organization, role, revision, and hash.
3. `request_document` and `mark_unresolved` keep the issue blocking.
4. `accept_evidence`, `reject_evidence`, or `correct_mapping` invalidate the affected calculation and package.
5. The exact paused run resumes, or a new durable run is queued for the same current revision.
6. The deterministic calculator recomputes from the accepted decision and authoritative evidence.
7. The new calculation, coverage, certificate draft, and events are persisted.
8. Only a completed current run with zero blocking issues and a current calculation/package hash may enter `ready_for_officer_review`.
9. Officer approval binds to that exact revision and package hash. A stale result, stale hash, `waiting_review` run, or missing calculation must be rejected by the backend even if the frontend is bypassed.

The frontend displays the transition as: decision recorded -> recalculating -> controls rechecked -> revised draft ready. It must never optimistically display success.

## Other QA gaps included in the redesign

- Curated templates must be immutable. Opening a prepared case creates a derived working case, or the interface provides an explicit reset that restores the original fixture. QA or demo actions must not change the template for later users.
- Viewer controls must be disabled or hidden for case creation, upload, review resolution, amendment creation, and approval. The reason and required role remain visible.
- Generated assistant language must say “internally approved draft,” not “sign the final certificate.”
- A displayed legacy result from an earlier revision must be labelled stale and must not appear as the current result.
- Hosted Supabase mode must show the real sign-in form. Offline identity controls appear only when the API and frontend are both in explicit offline mode.
- CopilotKit Inspector and development-only chrome must be disabled in the demo build.

## Visual system

- Tone: institutional, calm, precise, high-trust.
- Base: deep graphite/navy application chrome with warm neutral reading surfaces.
- Evidence: restrained blue.
- Running: cool cyan or blue with subtle motion.
- Review: amber.
- Failed control or breach: red.
- Verified current result only: green.
- Stale/superseded: gray with strike or stamp treatment.
- Typography: clean sans-serif for interface and conversation, tabular mono for numbers, hashes, clauses, and event labels. Avoid decorative editorial headings inside operational views.
- Surfaces: thin borders, low-radius panels, limited shadow, no glass, neon gradients, oversized hero type, or uniform card grids.
- Motion: stage transitions, artifact arrival, and review-resume only. Respect reduced motion.

## Error handling

- API unavailable: keep the last snapshot, show disconnected state, and offer retry.
- Authentication expired: stop private calls and present sign-in without repeated 401 console noise.
- Stale command: refresh the case and explain what changed.
- Failed tool or node: attach the error to its workflow stage and expose safe retry when allowed.
- Upload rejected: preserve the selected metadata and explain the exact file problem.
- Event gap: reload snapshot and replay after the last durable sequence.

## Acceptance criteria

- A first-time judge can identify the current case, active stage, blocker, and next action within 15 seconds.
- The complete document -> interpretation -> evidence -> calculation -> review -> revised draft flow appears as one conversation.
- Every result number can reveal its source or deterministic calculation line.
- Review resolution cannot produce a ready or approved package before recomputation finishes.
- Prepared templates remain unchanged after a demo run.
- Viewer mode exposes no enabled privileged mutations.
- The UI has no horizontal page scroll or clipped controls at 1024 and 1440 px.
- Widths below 1024 px show the desktop-required state rather than a compressed workflow.
- Keyboard focus follows new interrupts and returns to the triggering control when a dialog or rail closes.
- Status never relies on color alone.
- Browser console has no application errors during the main demo flow.
- Production build, frontend tests, and Playwright journeys pass for scoped pass, breach, review/resume, amendment invalidation, unauthorized role, reconnect, and desktop viewport behavior.

## Non-goals

- A general-purpose agent builder or coding IDE.
- A marketing landing page inside the authenticated product.
- Free-form chat actions that bypass finance controls.
- Server-side electronic signatures or lender delivery.
- Hiding missing backend behavior behind recorded frontend animations.
- A mobile or phone workflow for the hackathon version.
