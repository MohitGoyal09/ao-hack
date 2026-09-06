"use client";

import { useEffect, useRef, useState } from "react";
import { Streamdown } from "streamdown";
import {
  docId, Job, post, Revision, RunResult, short, Snapshot, TERMINAL_JOB_STATES, UploadResult, useAction,
} from "@/lib/api";
import { canApprove, canMutate, PHASE_LABEL, recalcPhase, roleExplanation } from "@/lib/workflow";
import { StatusBadge } from "./StatusBadge";
import { ReviewInbox } from "@/components/ReviewInbox";
import { RevisionPanel } from "@/components/RevisionPanel";
import { OfficerApproval } from "@/components/OfficerApproval";
import { DownloadPackage } from "@/components/DownloadPackage";
import type { DomainEvent } from "@/components/EventFeed";
import { ArtifactCard, ConfirmationCard, TaskCard, ToolCard } from "@/components/ai-elements/workflow-cards";
import { useTranscript } from "@/components/ai-elements/transcript";
import s from "./workspace.module.css";

type Props = {
  caseId: string;
  caseName: string | null;
  snapshot: Snapshot | null;
  jobs: Job[];
  events: DomainEvent[];
  revisions: Revision[];
  error: string;
  disconnected: boolean;
  active: boolean;
  role: string;
  uploaded: UploadResult | null;
  refresh: () => Promise<void>;
  onSelectSource: (source: string | null) => void;
};

function Gated({ allowed, needed, label, children }: { allowed: boolean; needed: string; label: string; children: React.ReactNode }) {
  if (allowed) return <>{children}</>;
  return (
    <div className={s.gated}>
      <p className={s.gateNote} role="note">{roleExplanation(needed)} {label}</p>
      <div aria-disabled="true" className={s.gatedOff}>{children}</div>
    </div>
  );
}

type Rule = { external_rule_id: string; covenant_type: string; support_state: string; comparator: string; threshold: string; measurement_period: string; structured_rule?: { formula?: string }; source_spans?: { kind: string; section?: string; page?: number | null; sha256?: string }[] };
type Fact = { fact_key: string; amount: string; currency: string; unit_scale: number; period_start: string; period_end: string; evidence_state: string; source_spans?: { locator: string }[] };

const EVENT_SUMMARY: Record<string, (p: Record<string, unknown>) => string> = {
  REVISION_CREATED: () => "Revision opened — inputs hashed and locked",
  DOCUMENT_UPLOADED: (p) => `Document ${p.document_id} v${p.version} accepted as an immutable version`,
  RUN_STARTED: (p) => `Worker leased job ${p.job_id}`,
  DOCUMENT_READ: () => "Uploaded document opened from private storage",
  AGREEMENT_RESOLVED: () => "Controlling agreement identified",
  DEFINITIONS_COMPILED: (p) => `Covenant definition compiled (${p.rule_id ?? "current rule"})`,
  EVIDENCE_MAPPED: (p) => `${p.fact_count ?? "Financial"} evidence items mapped to the definition`,
  CALCULATION_STARTED: () => "Deterministic covenant calculator started",
  RUN_RETRIED: (p) => `Job ${p.job_id} retried (attempt ${p.attempt})`,
  CALCULATION_COMPLETED: (p) => `Deterministic calculation stored — ratio ${p.ratio} against threshold ${p.threshold}`,
  RECALCULATION_COMPLETED: () => "Post-review recalculation completed for the current revision",
  REVIEW_REQUIRED: () => "Human review required — nothing defaulted to zero",
  REVIEW_RESOLVED: (p) => `Review decision recorded (${p.decision_kind ?? "decision"})`,
  RESULT_INVALIDATED: () => "Prior results marked stale by an input change",
  APPROVAL_INVALIDATED: () => "Prior approval no longer binds the head revision",
  PACKAGE_REVISED: () => "Revised draft package persisted for the current revision",
  RUN_COMPLETED: (p) => `Run finished: ${p.status}`,
  RUN_FAILED: () => "Run failed — error attached to its stage",
  EVIDENCE_FOUND: (p) => `Evidence discovered: ${p.fact_key ?? p.label ?? "fact"}`,
  DEFINITION_RESOLVED: (p) => `Definition resolved: ${p.rule_id ?? "rule"}`,
  APPROVAL_RECORDED: () => "Officer approval locked the exact numbers",
  TOOL_CALL_STARTED: (p) => `Tool started: ${p.tool_name ?? p.label ?? "tool"}`,
  TOOL_CALL_COMPLETED: (p) => `Tool finished: ${p.tool_name ?? p.label ?? "tool"}`,
  TOOL_CALL_FAILED: (p) => `Tool failed: ${p.tool_name ?? p.label ?? "tool"}`,
};
const eventSummary = (e: DomainEvent) => (EVENT_SUMMARY[e.event_type] ?? (() => e.event_type))(e.payload ?? {});
const PIPELINE_EVENT_TITLE: Record<string, string> = {
  DOCUMENT_READ: "Read source document",
  AGREEMENT_RESOLVED: "Resolve governing agreement",
  DEFINITIONS_COMPILED: "Compile covenant definitions",
  EVIDENCE_MAPPED: "Map financial evidence",
  CALCULATION_STARTED: "Calculate covenant ratio",
  CALCULATION_COMPLETED: "Calculate covenant ratio",
};

function toolPresentation(message: { name?: string; content: string }) {
  try {
    const payload = JSON.parse(message.content);
    if (Array.isArray(payload)) return { title: "List covenant cases", summary: `${payload.length} available cases returned` };
    if (payload?.run_id && payload?.calculation) return { title: "Run covenant calculation", summary: `${payload.status ?? "Result"} · ${payload.calculation.ratio} ${payload.calculation.comparator} ${payload.calculation.threshold}` };
    if (payload?.document_kind) return { title: "Ingest covenant document", summary: `${payload.document_kind} · ${payload.extraction_state ?? "extracted"}` };
  } catch { /* The expandable result remains available for non-JSON tools. */ }
  return { title: message.name && message.name !== "Agent tool" ? message.name.replaceAll("_", " ") : "Covenant tool", summary: "Structured result received" };
}

function ResponseActions({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const copy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "covenant-agent-response.md";
    anchor.click();
    URL.revokeObjectURL(url);
  };
  return <div className={s.responseActions} aria-label="Response actions">
    <button type="button" onClick={copy} aria-label="Copy response" title="Copy response">{copied ? "✓" : "□"}<span>{copied ? "Copied" : "Copy"}</span></button>
    <button type="button" onClick={download} aria-label="Download response as Markdown" title="Download Markdown">↓<span>Download</span></button>
    <span className={s.actionDivider} />
    <button type="button" className={feedback === "up" ? s.actionSelected : ""} onClick={() => setFeedback(feedback === "up" ? null : "up")} aria-pressed={feedback === "up"} aria-label="Helpful response" title="Helpful">↑</button>
    <button type="button" className={feedback === "down" ? s.actionSelected : ""} onClick={() => setFeedback(feedback === "down" ? null : "down")} aria-pressed={feedback === "down"} aria-label="Unhelpful response" title="Not helpful">↓</button>
  </div>;
}

export function ChatTranscript({ caseName }: { caseName: string | null }) {
  const messages = useTranscript();
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => { bottom.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [messages.length, messages.at(-1)?.content]);
  if (!messages.length) return null;
  return <section className={s.chatTranscript} aria-label="Agent conversation" aria-live="polite">
    {messages.map((message) => {
      if (message.role === "tool") {
        const tool = toolPresentation(message);
        return <ToolCard key={message.id} title={tool.title} state={message.status === "streaming" ? "running" : "complete"} summary={message.status === "streaming" ? "Calling an authorized case tool" : tool.summary} output={<details className={s.toolResult}><summary>Inspect structured result</summary><pre>{message.content}</pre></details>} />;
      }
      return <article key={message.id} className={message.role === "user" ? s.userMessage : s.agentMessage}>
      <div className={s.messageAvatar} aria-hidden="true">{message.role === "user" ? "Y" : "C"}</div>
      <div className={s.messageContent}>
        <span>{message.role === "user" ? "You" : "Covenant agent"}</span>
        {message.role === "assistant" ? <Streamdown className={s.markdown} mode={message.status === "streaming" ? "streaming" : "static"} controls={false}>{message.content || (message.status === "streaming" ? "Working with the case record…" : `Working with ${caseName ?? "the covenant record"}.`)}</Streamdown> : <p>{message.content}</p>}
        {message.status === "streaming" && <small className={s.streamingState}><i /><i /><i /> Reviewing the evidence</small>}
        {message.role === "assistant" && message.status !== "streaming" && message.content && <ResponseActions content={message.content} />}
      </div>
    </article>;})}
    <div ref={bottom} />
  </section>;
}

export function Conversation({ caseId, caseName, snapshot, jobs, events, revisions, error, disconnected, active, role, uploaded, refresh, onSelectSource }: Props) {
  const { run: recalcRun, busy, error: runError } = useAction(refresh);
  const [result, setResult] = useState<RunResult | null>(null);
  const [locked, setLocked] = useState<import("@/lib/api").Approval | null>(null);
  const open = snapshot?.open_review_issues ?? 0;
  const mutate = canMutate(role);

  const recalculate = () => recalcRun(async () => { setResult(await post<RunResult>(`/cases/${caseId}/run`, {})); await refresh(); });

  const rules = (snapshot?.covenant_rules ?? []) as Rule[];
  const facts = (snapshot?.financial_facts ?? []) as Fact[];
  const calc = snapshot?.artifacts?.calculation;
  const lastResolved = events.filter((e) => e.event_type === "REVIEW_RESOLVED").map((e) => e.sequence).pop() ?? null;
  const phase = recalcPhase(lastResolved, events, snapshot);
  const toolEvents = events.filter((e) => e.event_type.startsWith("TOOL_CALL_") || e.event_type in PIPELINE_EVENT_TITLE).slice(-8);
  const pipelineStarted = jobs.length > 0 || events.some((e) => ["RUN_STARTED", "RUN_RETRIED", "DEFINITION_RESOLVED", "EVIDENCE_FOUND", "CALCULATION_COMPLETED", "RECALCULATION_COMPLETED", "REVIEW_REQUIRED", "RUN_COMPLETED", "RUN_FAILED"].includes(e.event_type));
  const reviewVisible = open > 0 || result?.status === "NEEDS_REVIEW";
  const revisionVisible = revisions.length > 1 || events.some((e) => ["INPUT_CHANGED", "RESULT_INVALIDATED", "APPROVAL_INVALIDATED"].includes(e.event_type));

  return (
    <>
      {disconnected && <div className={`${s.banner} ${s.bannerError}`} role="alert">API unavailable — showing the last snapshot. <button type="button" className={s.citeButton} onClick={refresh}>Retry</button></div>}
      {error && !disconnected && <div className={`${s.banner} ${s.bannerError}`} role="alert">{error}</div>}

      <section className={s.caseHeader} aria-label="Case overview">
        <p className={s.kicker}>Covenant review</p>
        <h1>{caseName ?? caseId}</h1>
        {snapshot && <div className={s.chipRow}><StatusBadge state={snapshot.run_state} label={snapshot.run_state.replaceAll("_", " ")} /><StatusBadge state={snapshot.coverage.state} label={`coverage ${snapshot.coverage.state.replaceAll("_", " ")}`} /><span className={s.caseRevision}>{snapshot.revision.revision_id}</span></div>}
      </section>
      <ChatTranscript caseName={caseName} />
      {!pipelineStarted ? <TaskCard title="Ready for intake" active={false} steps={[
        { label: "Attach the credit agreement or choose a prepared case", state: "pending" },
        { label: "Resolve the governing agreement and definitions", state: "pending" },
        { label: "Map evidence and calculate the covenant", state: "pending" },
      ]} /> : <>
        <TaskCard title={active || busy ? "Covenant review in progress" : "Covenant review record"} active={active || busy} steps={[
          { label: "Document intake", state: snapshot?.documents.length ? "done" : active ? "active" : "pending" },
          { label: "Agreement and amendment resolution", state: rules.length ? "done" : active ? "active" : "pending" },
          { label: "Evidence mapping", state: (calc || result) ? "done" : active ? "active" : "pending" },
          { label: "Deterministic calculation", state: (calc || result) ? "done" : active ? "active" : "pending" },
        ]} />
        {snapshot && snapshot.documents.length > 0 && <ArtifactCard title={`${snapshot.documents.length} source document${snapshot.documents.length === 1 ? "" : "s"}`} subtitle={uploaded ? uploaded.job_id ? `Attached to ${uploaded.revision_id} · background job ${short(uploaded.job_id)}` : `Registered on ${uploaded.revision_id} · waiting for the agent's next tool` : "Immutable versions feed the audit trail."}><ul className={s.compactList}>{snapshot.documents.map((document) => <li key={docId(document)}><code>{docId(document)}</code></li>)}</ul></ArtifactCard>}
        {jobs.slice(-3).reverse().map((job) => <ToolCard key={job.job_id} title="Run deterministic controls" state={job.state === "failed" ? "error" : job.state === "completed" ? "complete" : job.state === "queued" ? "queued" : "running"} summary={job.state === "failed" ? "Control run needs a retry" : `Revision ${job.revision_id} · attempt ${job.attempt_count}`} output={<p>{job.state === "failed" ? "Retry the calculation. Technical logs are kept in case history." : TERMINAL_JOB_STATES.has(job.state) ? "Control stage finished." : "Processing in the background."}</p>} />)}
        {toolEvents.map((event) => {
          const historicalStart = event.event_type.endsWith("STARTED") && (!active || (event.event_type === "CALCULATION_STARTED" && Boolean(calc)));
          const state = event.event_type.endsWith("FAILED") ? "error" : event.event_type.endsWith("STARTED") && !historicalStart ? "running" : "complete";
          return <ToolCard key={event.sequence} title={PIPELINE_EVENT_TITLE[event.event_type] ?? String(event.payload?.tool_name ?? "Covenant agent tool")} state={state} summary={eventSummary(event).replace(/undefined/g, "current revision")} input={<code>Revision {event.revision_id ?? snapshot?.revision.revision_id ?? "current"}</code>} output={<p>{eventSummary(event).replace(/undefined/g, "current revision")}</p>} />;
        })}
        {!calc && !result && !reviewVisible && <ToolCard title="Calculate covenant ratio" state={busy ? "running" : "queued"} summary={busy ? "Applying deterministic controls" : "Ready when evidence is mapped"} output={<Gated allowed={mutate} needed="treasury_reviewer, officer or admin" label="Calculation is disabled."><button type="button" className={s.primaryButton} onClick={recalculate} disabled={busy}>{busy ? "Running controls…" : "Run calculation"}</button></Gated>} />}
        {runError && <ToolCard title="Calculation retry" state="error" summary="The calculation request did not complete" output={<p>{runError}</p>} />}
      </>}
      {(calc || result) && <ArtifactCard title="Deterministic covenant calculation" subtitle="Typed arithmetic is repeatable. Agreement interpretation and evidence remain cited.">
        {calc ? <div className={s.calculationGrid}><div><span>Ratio</span><strong>{calc.ratio}×</strong></div><div><span>Threshold</span><strong>{calc.comparator} {calc.threshold}×</strong></div><div className={s.calculationWide}><span>Inputs</span><code>{Object.entries(calc.inputs).map(([key, value]) => `${key}=${value}`).join(" · ")}</code></div><div className={s.calculationWide}><span>Sources</span>{rules.slice(0, 3).map((rule) => <button key={rule.external_rule_id} type="button" className={s.citeButton} onClick={() => onSelectSource(rule.external_rule_id)}>{rule.external_rule_id}</button>)}</div></div> : <p className={s.emptyIntro}>Calculation output is being saved.</p>}
        {result && <p className={s.resultReason}>{result.status_reason}</p>}
      </ArtifactCard>}
      {snapshot && reviewVisible && <ConfirmationCard state="required" title="A controller decision is required" detail="Evidence validation found a condition that requires human judgment. Nothing is assumed or defaulted."><Gated allowed={mutate} needed="treasury_reviewer, officer or admin" label="Review decisions are disabled."><ReviewInbox caseId={caseId} snapshot={snapshot} onChange={refresh} /></Gated></ConfirmationCard>}
      {lastResolved != null && <ConfirmationCard state="resolved" title={PHASE_LABEL[phase]} detail="The decision is bound to this revision. Recalculation must finish before approval."><TaskCard title="Recheck current revision" active={phase !== "ready"} steps={(["recorded", "recalculating", "rechecked", "ready"] as const).map((step, index) => ({ label: PHASE_LABEL[step], state: index < ["recorded", "recalculating", "rechecked", "ready"].indexOf(phase) ? "done" : step === phase ? "active" : "pending" }))} /></ConfirmationCard>}
      {snapshot && revisionVisible && <details className={s.collapsedAction}><summary>Revision history and amendment controls</summary><Gated allowed={mutate} needed="treasury_reviewer, officer or admin" label="Amendment recording is disabled."><RevisionPanel caseId={caseId} snapshot={snapshot} revisions={revisions} onChange={refresh} /></Gated></details>}
      {snapshot && (snapshot.package_state === "ready_for_officer_review" || snapshot.package_state === "approved_draft") && <ArtifactCard title="Draft ready for officer review" subtitle="This is an internally approved draft, never an e-signature or lender delivery."><Gated allowed={canApprove(role)} needed="officer or admin" label="Approval is disabled."><OfficerApproval caseId={caseId} snapshot={snapshot} result={result} role={role} approval={locked} onApproved={setLocked} onChange={refresh} /></Gated><DownloadPackage info={null} snapshot={snapshot} result={result} approval={locked} /></ArtifactCard>}

    </>
  );
}
