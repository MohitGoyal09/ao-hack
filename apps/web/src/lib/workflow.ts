"use client";

// Pure derivation helpers for the chat-first CFO workspace.
// Progress comes ONLY from persisted backend state (snapshot + durable
// events), never from timers or client-side guessing.

import type { Snapshot } from "@/lib/api";

export type StageState = "pending" | "running" | "blocked" | "complete" | "failed" | "stale";

export type StageDef = { id: string; title: string; hint: string };

export const STAGES: StageDef[] = [
  { id: "documents", title: "Documents received", hint: "Agreement, amendments and financials on file" },
  { id: "agreement", title: "Governing agreement resolved", hint: "Controlling document chain identified" },
  { id: "definitions", title: "Covenant definitions compiled", hint: "Rulebook extracted with citations" },
  { id: "evidence", title: "Financial evidence mapped", hint: "Facts mapped to contractual components" },
  { id: "calculation", title: "Ratio calculated", hint: "Deterministic Decimal computation" },
  { id: "review", title: "Controller review", hint: "Open judgment calls resolved" },
  { id: "package", title: "Draft package prepared", hint: "Internally approved draft ready" },
];

export type EventLike = {
  sequence: number;
  event_type: string;
  revision_id?: string | null;
  payload?: Record<string, unknown>;
};

const CALC_DONE = new Set(["CALCULATION_COMPLETED", "RECALCULATION_COMPLETED"]);
const INVALIDATING = new Set(["RESULT_INVALIDATED", "INPUT_CHANGED", "REVISION_CREATED", "DOCUMENT_UPLOADED", "APPROVAL_INVALIDATED"]);

const lastSeq = (events: EventLike[], types: Set<string>) => {
  let seq = 0;
  for (const e of events) if (types.has(e.event_type) && e.sequence > seq) seq = e.sequence;
  return seq;
};

/** True when an invalidation happened after the latest stored calculation. */
export function isInvalidated(events: EventLike[]): boolean {
  const calculation = lastSeq(events, CALC_DONE);
  return calculation > 0 && lastSeq(events, INVALIDATING) > calculation;
}

export type StageStatus = { id: string; title: string; hint: string; state: StageState; detail: string; action: string };

export function deriveStages(snapshot: Snapshot | null, events: EventLike[]): StageStatus[] {
  const base = (id: string): StageStatus => {
    const def = STAGES.find((s) => s.id === id)!;
    return { ...def, state: "pending", detail: "Waiting for the pipeline.", action: "Upload a governing document to start." };
  };
  if (!snapshot) return STAGES.map((s) => ({ ...s, state: "pending" as StageState, detail: "No case loaded.", action: "Open a case to begin." }));

  const docs = Array.isArray(snapshot.documents) ? snapshot.documents.length : 0;
  const rules = Array.isArray(snapshot.covenant_rules) ? (snapshot.covenant_rules as unknown[]).length : 0;
  const facts = Array.isArray(snapshot.financial_facts) ? (snapshot.financial_facts as unknown[]).length : 0;
  const hasCalc = !!snapshot.artifacts?.calculation;
  const open = snapshot.open_review_issues ?? 0;
  const run = snapshot.run_state;
  const pkg = snapshot.package_state;
  const running = run === "queued" || run === "running";
  const failed = run === "failed" || run === "cancelled";
  const stale = isInvalidated(events);
  const currentApproval = (snapshot.approvals ?? []).some((a) => !a.superseded && a.decision === "approved" && a.target_revision === snapshot.revision.revision_id);
  const currentRevisionEvents = events.filter((event) => !event.revision_id || event.revision_id === snapshot.revision.revision_id);
  const lastEvent = currentRevisionEvents.at(-1)?.event_type;
  const runningStage = !running ? null
    : lastEvent === "DOCUMENT_READ" ? "agreement"
    : lastEvent === "AGREEMENT_RESOLVED" ? "definitions"
    : lastEvent === "DEFINITIONS_COMPILED" ? "evidence"
    : lastEvent === "EVIDENCE_MAPPED" || lastEvent === "CALCULATION_STARTED" ? "calculation"
    : lastEvent === "REVIEW_RESOLVED" ? "review"
    : "agreement";

  const out: StageStatus[] = [];

  // 1 Documents received
  {
    const s = base("documents");
    if (docs > 0) { s.state = "complete"; s.detail = `${docs} document(s) on file.`; s.action = "Review sources in the Evidence tab."; }
    else if (failed) { s.state = "failed"; s.detail = "Run failed before intake completed."; s.action = "Check the error on the run, then retry."; }
    else if (running) { s.state = "running"; s.detail = "Worker is reading uploaded documents."; s.action = "Wait for intake to finish."; }
    else { s.detail = "No documents on file for this case."; s.action = "Upload a governing document to start."; }
    out.push(s);
  }
  // 2 Governing agreement resolved
  {
    const s = base("agreement");
    if (rules > 0) { s.state = "complete"; s.detail = `${rules} covenant rule(s) extracted with citations.`; s.action = "Inspect cited clauses below."; }
    else if (failed) { s.state = "failed"; s.detail = "Run failed before the agreement was resolved."; s.action = "Check the run error and retry."; }
    else if (runningStage === "agreement" && docs > 0) { s.state = "running"; s.detail = "Resolving the controlling document chain."; s.action = "Wait for extraction."; }
    else if (open > 0) { s.state = "blocked"; s.detail = `${open} open review issue(s) block agreement resolution.`; s.action = "Resolve the review interrupt in the conversation."; }
    else { s.detail = "No extracted rulebook yet."; s.action = "Upload a credit agreement to extract definitions."; }
    out.push(s);
  }
  // 3 Covenant definitions compiled
  {
    const s = base("definitions");
    if (rules > 0) { s.state = "complete"; s.detail = "Active definition chain compiled from cited clauses."; s.action = "Open the calculation card for the formula."; }
    else if (failed) { s.state = "failed"; s.detail = "Definition extraction failed."; s.action = "Check the run error and retry."; }
    else if (runningStage === "definitions" && docs > 0) { s.state = "running"; s.detail = "Compiling covenant definitions."; s.action = "Wait for extraction."; }
    else if (open > 0) { s.state = "blocked"; s.detail = "Missing evidence blocks definition sign-off."; s.action = "Resolve the review interrupt."; }
    else { s.detail = "Definitions not yet compiled."; s.action = "Upload a credit agreement first."; }
    out.push(s);
  }
  // 4 Financial evidence mapped
  {
    const s = base("evidence");
    if (facts > 0) { s.state = "complete"; s.detail = `${facts} financial fact(s) mapped to contract components.`; s.action = open > 0 ? "Review the mapped evidence before relying on it." : "Verify sources in the Evidence tab."; }
    else if (run === "waiting_review" || open > 0) { s.state = "blocked"; s.detail = "Evidence is missing or unclear; the run is paused for review."; s.action = "Resolve the review interrupt in the conversation."; }
    else if (failed) { s.state = "failed"; s.detail = "Evidence mapping failed."; s.action = "Check the run error and retry."; }
    else if (runningStage === "evidence") { s.state = "running"; s.detail = "Mapping financial facts to contract components."; s.action = "Wait for mapping."; }
    else { s.detail = "No financial facts mapped yet."; s.action = "Upload a financial package."; }
    out.push(s);
  }
  // 5 Ratio calculated
  {
    const s = base("calculation");
    if (!hasCalc && stale) { s.state = "stale"; s.detail = "Prior calculation was invalidated by a newer input; recomputation is pending."; s.action = "Wait for the worker, then resolve any review issue."; }
    else if (hasCalc && stale) { s.state = "stale"; s.detail = "This number belongs to a superseded input bundle."; s.action = "Wait for recomputation — do not rely on the old ratio."; }
    else if (hasCalc) { s.state = "complete"; s.detail = open > 0 ? "Calculation stored; human review is required before it can support a package." : "Deterministic calculation stored for the current revision."; s.action = open > 0 ? "Resolve the controller review next." : "Trace every input to its source below."; }
    else if (failed) { s.state = "failed"; s.detail = "Calculation failed."; s.action = "Check the run error and retry."; }
    else if (runningStage === "calculation") { s.state = "running"; s.detail = "Deterministic calculator is running."; s.action = "Wait for the ratio."; }
    else if (open > 0) { s.state = "blocked"; s.detail = "Missing evidence blocks calculation."; s.action = "Resolve the review interrupt."; }
    else { s.detail = "No calculation yet for this revision."; s.action = "Press Recalculate on the workbench card."; }
    out.push(s);
  }
  // 6 Controller review
  {
    const s = base("review");
    if (stale && open > 0) { s.state = "blocked"; s.detail = `${open} open issue(s) after an input change.`; s.action = "Resolve the review interrupt with a recorded rationale."; }
    else if (!hasCalc && stale) { s.state = "stale"; s.detail = "Review state was invalidated by a newer input."; s.action = "Wait for recomputation."; }
    else if (open > 0 || run === "waiting_review") { s.state = "blocked"; s.detail = `${open} open review issue(s) need a named decision.`; s.action = "Resolve the review interrupt in the conversation."; }
    else if (failed) { s.state = "failed"; s.detail = "Run failed during review."; s.action = "Check the run error and retry."; }
    else if (runningStage === "review") { s.state = "running"; s.detail = "Worker is rechecking controls."; s.action = "Wait for controls to be rechecked."; }
    else if (hasCalc && run === "completed") { s.state = "complete"; s.detail = "Zero blocking issues on the current run."; s.action = "Proceed to the internally approved draft."; }
    else { s.detail = "Review has not started for this revision."; s.action = "Run the pipeline first."; }
    out.push(s);
  }
  // 7 Draft package prepared
  {
    const s = base("package");
    if (stale && !currentApproval) { s.state = "stale"; s.detail = `Package ${shortHash(snapshot.package_hash)} belongs to superseded inputs.`; s.action = "Wait for the revised draft — do not approve the old package."; }
    else if (pkg === "approved_draft" && currentApproval) { s.state = "complete"; s.detail = "Internally approved draft bound to this revision and package hash."; s.action = "Download or print the draft package."; }
    else if (pkg === "ready_for_officer_review" && open === 0 && run === "completed") { s.state = "complete"; s.detail = "Revised draft ready for officer review."; s.action = "An officer approves the exact locked numbers below."; }
    else if (open > 0) { s.state = "blocked"; s.detail = "Open review issues keep the draft unready."; s.action = "Resolve the review interrupt first."; }
    else if (failed) { s.state = "failed"; s.detail = "Package generation failed."; s.action = "Check the run error and retry."; }
    else if (running) { s.state = "running"; s.detail = "Preparing the revised draft package."; s.action = "Wait for the package."; }
    else { s.detail = `Package state: ${pkg}.`; s.action = "Complete calculation and review first."; }
    out.push(s);
  }
  return out;
}

const shortHash = (h: string | null | undefined) => (h ? `${h.slice(0, 12)}…` : "—");

// Viewer read-only; treasury_reviewer+ mutate; officer|admin approve.
export const canMutate = (role: string) => role === "treasury_reviewer" || role === "officer" || role === "admin";
export const canApprove = (role: string) => role === "officer" || role === "admin";
export const roleExplanation = (needed: string) => `Requires role: ${needed}. Your identity is read-only for this action.`;

// Recalculation phase after a review decision. Driven ONLY by durable
// events + snapshot state — never by the resolve HTTP response alone.
export type RecalcPhase = "idle" | "recorded" | "recalculating" | "rechecked" | "ready";

export function recalcPhase(
  decisionSequence: number | null,
  events: EventLike[],
  snapshot: Snapshot | null,
): RecalcPhase {
  if (decisionSequence == null) return "idle";
  const after = events.filter((e) => e.sequence > decisionSequence);
  const started = after.some((e) => e.event_type === "RUN_STARTED" || e.event_type === "RUN_RETRIED" || e.event_type === "RECALCULATION_COMPLETED" || e.event_type === "CALCULATION_COMPLETED");
  const runningNow = snapshot?.run_state === "queued" || snapshot?.run_state === "running";
  const calcDone = after.some((e) => CALC_DONE.has(e.event_type));
  const ready = !!snapshot && (snapshot.package_state === "ready_for_officer_review" || snapshot.package_state === "approved_draft") && snapshot.run_state === "completed" && (snapshot.open_review_issues ?? 0) === 0;
  if (ready) return "ready";
  if (calcDone) return "rechecked";
  if (started || runningNow) return "recalculating";
  return "recorded";
}

export const PHASE_LABEL: Record<RecalcPhase, string> = {
  idle: "No decision in flight",
  recorded: "Decision recorded",
  recalculating: "Recalculating",
  rechecked: "Controls checked",
  ready: "Revised draft ready",
};
