# Institutional Agent Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present the covenant agent as a clear, evidence-led institutional workflow with synchronized tool activity, documents, calculations, review gates, and progress.

**Architecture:** Keep the existing durable event and snapshot contracts as the single source of truth. Derive both the central conversation record and right context rail from those contracts, while introducing small view helpers for human-readable documents, calculations, and stage states. The LLM remains the planner; deterministic code remains limited to typed tools, arithmetic, integrity, and authorization gates.

**Tech Stack:** Next.js 16, React 19, TypeScript, CSS modules, CopilotKit/AG-UI, Streamdown, FastAPI/LangGraph backend.

**Spec:** `docs/agent-interaction-flow.md`

## Global Constraints

- Do not invent stage progress in the browser; use persisted snapshots and durable events.
- Do not expose raw prompts, document bodies, storage paths, credentials, or hidden chain-of-thought.
- Keep the draft clearly separate from an e-signature or lender-delivered certificate.
- A missing or unclear value must block or request review; it must never become zero.
- Preserve the existing upload, review, revision, approval, and package APIs.
- Use responsive two-column layouts for comparable values and collapse them to one column when space is narrow.

---

### Task 1: Normalize the institutional information model

**Files:**
- Modify: `apps/web/src/lib/workflow.ts`
- Modify: `apps/web/src/components/workspace/Conversation.tsx`
- Modify: `apps/web/src/components/workspace/ContextRail.tsx`

**Interfaces:**
- Consumes: `Snapshot`, `DomainEvent`, and existing `deriveStages` results.
- Produces: human-readable stage copy, document labels, calculation conclusions, and matching anchors for the conversation and rail.

- [ ] Add pure helpers for document labels, active stage selection, and calculation result wording.
- [ ] Ensure pending, running, blocked, failed, stale, and complete states are derived only from persisted state.
- [ ] Give each displayed section an anchor that the right rail can open.
- [ ] Run `npm run build` in `apps/web` and fix all type errors.

### Task 2: Build clear conversation and evidence cards

**Files:**
- Modify: `apps/web/src/components/workspace/Conversation.tsx`
- Modify: `apps/web/src/components/ai-elements/workflow-cards.tsx`
- Modify: `apps/web/src/components/ai-elements/workflow-cards.module.css`

**Interfaces:**
- Consumes: normalized tool events, snapshot documents, rules, facts, and calculation.
- Produces: chronological tool cards, document inventory, calculation explanation, and human decision cards.

- [ ] Present each tool with purpose, input, result, and semantic status.
- [ ] Present attached documents using readable names and roles instead of only identifiers.
- [ ] Present calculation ratio, contractual limit, formula inputs, source citations, and plain-language conclusion in a two-column evidence layout.
- [ ] Keep raw structured tool output inside an optional disclosure.
- [ ] Run `npm run build` in `apps/web`.

### Task 3: Synchronize and simplify the context rail

**Files:**
- Modify: `apps/web/src/components/workspace/ContextRail.tsx`
- Modify: `apps/web/src/components/workspace/workspace.module.css`

**Interfaces:**
- Consumes: the same `deriveStages(snapshot, events)` output used by the main record.
- Produces: a compact progress timeline plus readable outputs and source context.

- [ ] Render one current-stage summary and a seven-step semantic timeline.
- [ ] Use visible running animation only for the active persisted stage.
- [ ] Strike completed labels, use green for complete, amber for blocked/review, red for failed, blue for running, and gray for pending/stale.
- [ ] Make document and citation rows actionable and keyboard accessible.
- [ ] Remove redundant top-level status badges from Outputs and Context.

### Task 4: Consolidate layout and responsive styling

**Files:**
- Modify: `apps/web/src/components/workspace/workspace.module.css`
- Modify: `apps/web/src/components/ai-elements/workflow-cards.module.css`

**Interfaces:**
- Consumes: existing workspace class names.
- Produces: a stable desktop workspace and narrow-screen fallbacks without horizontal overflow.

- [ ] Replace conflicting appended overrides with one final coherent institutional theme.
- [ ] Keep navigation, main record, and context visually distinct without heavy borders.
- [ ] Use two-column grids only for comparable data and collapse them below the available width.
- [ ] Keep the composer anchored, readable, and separate from scrolling evidence.
- [ ] Honor `prefers-reduced-motion` and visible keyboard focus.

### Task 5: Verify the complete demo contract

**Files:**
- Modify: `docs/agent-interaction-flow.md`
- Modify: `docs/agent-handoff.md`

**Interfaces:**
- Consumes: the finished UI and existing backend pipeline.
- Produces: exact demo instructions and an honest verification record.

- [ ] Run the full API unit test suite.
- [ ] Run the web production build and `git diff --check`.
- [ ] Run browser QA at desktop and narrow widths through create case, attach document, agent/tool progress, calculation, review, and context navigation where the local environment permits.
- [ ] Record the exact tested boundary and any unverified external service behavior.
- [ ] Request an independent TypeScript/code review and resolve material findings.
