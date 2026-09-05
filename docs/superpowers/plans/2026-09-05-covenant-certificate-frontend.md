# Covenant Certificate Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task.

**Goal:** Build a polished finance workbench that makes contract interpretation, evidence, deterministic calculation, and human review visible in under three minutes.

**Architecture:** Adapt the CopilotKit LangGraph FastAPI starter in `apps/web`. AG-UI synchronizes typed case state and review interrupts. The main interface is a domain workbench; chat is secondary.

**Tech Stack:** Next.js 16, React 19, TypeScript, CopilotKit, AG-UI, Tailwind CSS, Radix primitives, Recharts, React Flow for the definition graph, Vitest, Testing Library, Playwright.

**Spec:** `docs/covenant-certificate-backend-architecture.md`

## Visual direction

Use an institutional forensic-ledger style: warm off-white document surfaces, graphite navigation, restrained blue for evidence, amber for review, red for breach, and green only for proved compliance. Use a readable sans face for interface text and tabular numerals for calculations. Avoid generic gradients, floating chatbot cards, decorative glass, and card grids with equal visual weight.

The memorable moment is a split agreement comparison where one definition branch changes the same financial packet from pass to breach.

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
- [ ] Commit `feat: add finance review controls`.

## Task 8: Build the signature demo comparison

- [ ] Create split Agreement A and Agreement B columns over one shared financial packet.
- [ ] Synchronize scrolling and highlight only the definition branches that differ.
- [ ] Animate the result change after both deterministic calculations complete.
- [ ] Show the deciding clause, not agent narration, as the final visual focus.
- [ ] Provide a stable seeded demo route that never depends on live search.
- [ ] Commit `feat: add agreement comparison demo`.

## Task 9: Build certificate and evidence-package preview

- [ ] Render the agreement-specific draft certificate with a persistent DRAFT mark.
- [ ] Add tabs for certificate, calculation schedule, evidence manifest, approvals, and audit events.
- [ ] Allow signed URL download only after backend authorization.
- [ ] Show artifact hash and version when a source or decision changes.
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
- The same financial packet visibly produces two different contract outcomes.
- Every displayed number opens its source.
- Missing evidence blocks the result and creates a clear review action.
- No raw chain-of-thought, secret, or private document body appears in operational logs.
- The full demonstration works at 1440 pixels and the review path remains usable at 375 pixels.
