# Covenant Certificate Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task.

**Goal:** Build a polished finance workbench that makes contract interpretation, evidence, deterministic calculation, and human review visible in under three minutes.

**Architecture:** Adapt the CopilotKit LangGraph FastAPI starter in `apps/web`. AG-UI synchronizes typed case state and review interrupts. The main interface is a domain workbench; chat is secondary.

**Tech Stack:** Next.js 16, React 19, TypeScript, CopilotKit, AG-UI, Tailwind CSS, Radix primitives, Recharts, React Flow for the definition graph, Vitest, Testing Library, Playwright.

**Spec:** `docs/covenant-certificate-backend-architecture.md`

**Controlling revision:** `docs/implementation-contract.md`. Revision-aware results, declared coverage and server-authorized review take precedence over the earlier starter behavior. This is an implementation plan; no UI has yet been verified.

## Visual direction

Use an institutional forensic-ledger style: warm off-white document surfaces, graphite navigation, restrained blue for evidence, amber for review, red for breach, and green only for proved compliance. Use a readable sans face for interface text and tabular numerals for calculations. Avoid generic gradients, floating chatbot cards, decorative glass, and card grids with equal visual weight.

The main demonstration shows an amendment or financial update changing a case, the affected evidence path, an exception resolved by a human, and a revised draft package. The two-agreement view is a secondary, clearly labelled hypothetical comparison when contracts do not govern the same borrower.

## Task 1: Remove the starter demo and establish the design system

- [ ] Delete weather, proverb, todo, flight, and sample canvas behavior.
- [ ] Add typed color, spacing, typography, radius, shadow, and motion tokens in `apps/web/src/app/globals.css`.
- [ ] Create shared `StatusBadge`, `EvidenceLink`, `Money`, `Ratio`, `EmptyState`, `ErrorState`, and `Skeleton` components.
- [ ] Add Vitest and Testing Library. Test status colors, numeric formatting, keyboard focus, and accessible names.
- [ ] Commit `feat: establish covenant workbench design system`.

## Task 2: Build the application shell and case navigation

- [ ] Create a three-region desktop shell: case rail, central workbench, review/activity rail.
- [ ] Create a compact mobile layout with case drawer and review bottom sheet.
- [ ] Add case states, document counts, test period, and last activity to the case rail.
- [ ] Display run state, per-covenant result, assessed/unsupported scope and package approval separately. A failed supported test remains visible even when the package has other unresolved issues.
- [ ] Preserve a visible connection and processing state without exposing raw chain-of-thought.
- [ ] Test 375, 768, 1024, and 1440 pixel widths.
- [ ] Commit `feat: add covenant case workspace shell`.

## Task 3: Add authenticated case creation and document intake

- [ ] Connect Supabase Auth and protect all case routes.
- [ ] Build a guided upload surface for agreement, amendments, waiver, certificate form, and financial package.
- [ ] Show file kind, source, hash state, parse state, and replace-versus-add semantics.
- [ ] Prevent unsupported types and explain why a required document is missing.
- [ ] Test keyboard upload, drag and drop, duplicate file, parser failure, and cross-user access denial.
- [ ] Commit `feat: add covenant document intake`.

## Task 4: Connect AG-UI state and domain events

- [ ] Define frontend types for case, document, covenant, definition node, fact, calculation, review issue, certificate, and event.
- [ ] Map AG-UI events to a reducer with sequence and replay protection.
- [ ] Use revision IDs and a snapshot cursor. Ignore stale events for the active revision, retain them in history, and show old results as stale until the backend publishes a validated new result. Custom application events use AG-UI custom envelopes.
- [ ] Render named work stages: Documents, Policy, Evidence, Calculation, Control Review, Officer Review.
- [ ] Support reconnect from last event sequence and distinguish retryable connection failure from case failure.
- [ ] Commit `feat: stream covenant case state`.

## Task 5: Build the definition-graph workbench

- [ ] Render covenant, numerator, denominator, inclusion, exclusion, cap, condition, and amendment nodes.
- [ ] Clicking a node opens its exact clause and page locator beside the graph.
- [ ] Mark unresolved and superseded nodes without implying a verdict.
- [ ] Add a path-only mode that shows the calculation’s active definition chain.
- [ ] Test nested references, cycles, amendment replacement, empty graph, and large graph navigation.
- [ ] Commit `feat: visualize covenant definitions`.

## Task 6: Build financial evidence and calculation views

- [ ] Render each contractual component beside its mapped financial fact and source.
- [ ] Show period, entity scope, currency, scale, adjustment, cap, and reviewer state.
- [ ] Render deterministic intermediate calculations and final threshold comparison.
- [ ] Make unsupported add-backs visually block the result rather than appear as warnings below it.
- [ ] Test formatting with negative values, millions, percentages, long labels, and missing evidence.
- [ ] Commit `feat: show financial evidence and covenant math`.

## Task 7: Build human review interrupts

- [ ] Render one decision per interrupt with question, clause, evidence, alternatives, and result impact.
- [ ] Support approve with evidence, reject, correct mapping, request document, and mark unresolved.
- [ ] Require a reason and show the scope: case only, facility, or future cases.
- [ ] Display before and after calculations when a decision changes the result.
- [ ] Add a separate officer approval screen for the completed draft.
- [ ] Test authorization, double submission, stale decision, reconnect, rejection, and resumed workflow.
- [ ] Submit issue ID, revision ID, expected hash and idempotency key; on HTTP 409 refresh the issue and require renewed review. Never set an approved result optimistically from client shared state.
- [ ] Commit `feat: add finance review controls`.

## Task 8: Build the change-and-recheck demonstration

**Files:** create `apps/web/src/components/revisions/RevisionTimeline.tsx`, `ImpactPanel.tsx`, `ResultDiff.tsx`, and `apps/web/src/lib/cases/revision-state.ts`; test in `apps/web/src/lib/cases/revision-state.test.ts` and `apps/web/e2e/recheck.spec.ts`.

- [ ] Open a saved case, attach an applicable amendment or corrected financial packet, and create a new revision through the backend command.
- [ ] Highlight changed clauses and affected calculations. Show a historical result with a stale label while rerun is pending, never a premature green pass.
- [ ] Resolve a missing-evidence issue, wait for recalculation, and preview the revised package. Show invalidated prior approval and require approval for the new hash.
- [ ] Test wrong-facility amendment, newly added unsupported covenant, failed recalculation, stale review response, reconnect and rapid repeated upload.

### Secondary comparison view

- [ ] Create split Agreement A and Agreement B columns over one shared financial packet.
- [ ] Synchronize scrolling and highlight only the definition branches that differ.
- [ ] Animate the result change after both deterministic calculations complete.
- [ ] Show the deciding clause, not agent narration, as the final visual focus.
- [ ] Provide a stable seeded demo route that never depends on live search.
- [ ] Label recorded playback as playback, generated fixtures as synthetic and cross-borrower applications as hypothetical. Fixture selection must not hard-code the actual live result.
- [ ] Commit `feat: add agreement comparison demo`.

## Task 9: Build certificate and evidence-package preview

- [ ] Render the agreement-specific draft certificate with a persistent DRAFT mark.
- [ ] Add tabs for certificate, calculation schedule, evidence manifest, approvals, and audit events.
- [ ] Allow signed URL download only after backend authorization.
- [ ] Show artifact hash and version when a source or decision changes.
- [ ] Distinguish unsigned approved drafts from signed documents. List missing form sections and required officer statements; an exhibit reference alone does not supply a template.
- [ ] Commit `feat: preview covenant certificate package`.

## Task 10: Complete accessibility, error, and visual QA

- [ ] Ensure every status uses icon and text in addition to color.
- [ ] Test keyboard order, focus restoration after interrupts, dialogs, drawers, graph alternatives, and screen-reader labels.
- [ ] Add Playwright journeys for pass, breach, review, amendment, reconnect, and unauthorized access.
- [ ] Run responsive screenshots at 375, 768, 1024, and 1440 pixels in light and dark modes.
- [ ] Remove unused starter code and confirm no demo-user identity or public secret remains.
- [ ] Run production build, type check, unit tests, and Playwright tests.
- [ ] Commit `test: verify covenant workbench`.

## Frontend acceptance gate

- A judge understands the input, definition difference, calculation, result, and human boundary without reading chat.
- The primary demo completes update -> impact -> evidence review -> recalculation -> revised draft. A secondary comparison labels hypothetical outcomes clearly.
- Every displayed number opens its source.
- Missing evidence blocks the result and creates a clear review action.
- No raw chain-of-thought, secret, or private document body appears in operational logs.
- The full demonstration works at 1440 pixels and the review path remains usable at 375 pixels.
