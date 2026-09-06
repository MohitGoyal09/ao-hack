"use client";

import { useEffect, useRef, useState } from "react";
import { Streamdown } from "streamdown";
import {
  docId, DocumentMeta, Job, Revision, short, Snapshot, TERMINAL_JOB_STATES, UploadResult,
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
  documentMeta: Record<string, DocumentMeta>;
  refresh: () => Promise<void>;
  onSelectSource: (source: string | null) => void;
  onPreviewDocument: (document: DocumentMeta) => void;
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
  DOCUMENT_READ: (p) => `${p.filename ?? "Uploaded document"} opened from private storage`,
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
  DOCUMENT_READ: "Read PDF source",
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
    if (payload?.document_requirements) {
      const missing = payload.document_requirements.missing_required as string[] | undefined;
      return { title: "Inspect case readiness", summary: missing?.length ? `Needs ${missing.map((item) => item.replaceAll("_", " ")).join(" and ")}` : "Required documents are present" };
    }
    if (payload?.status === "awaiting_documents") return { title: "Check processing requirements", summary: `Waiting for ${(payload.missing_required as string[]).map((item) => item.replaceAll("_", " ")).join(" and ")}` };
    if (payload?.job_id && payload?.document_id) return { title: "Start document analysis", summary: `${payload.status ?? "Queued"} · revision ${payload.revision_id ?? "current"}` };
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

const roleName = (role?: string) => (role ?? "source document").replaceAll("_", " ");
const bytes = (size?: number) => size == null ? "Size unavailable" : size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`;
const calculationPasses = (ratio: number, comparator: string, threshold: number) => comparator.includes("<") ? ratio <= threshold : comparator.includes(">") ? ratio >= threshold : ratio === threshold;

export function Conversation({ caseId, caseName, snapshot, jobs, events, revisions, error, disconnected, active, role, uploaded, documentMeta, refresh, onSelectSource, onPreviewDocument }: Props) {
  const [locked, setLocked] = useState<import("@/lib/api").Approval | null>(null);
  const open = snapshot?.open_review_issues ?? 0;
  const mutate = canMutate(role);

  const rules = (snapshot?.covenant_rules ?? []) as Rule[];
  const facts = (snapshot?.financial_facts ?? []) as Fact[];
  const calc = snapshot?.artifacts?.calculation;
  const lastResolved = events.filter((e) => e.event_type === "REVIEW_RESOLVED").map((e) => e.sequence).pop() ?? null;
  const phase = recalcPhase(lastResolved, events, snapshot);
  const toolEvents = events.filter((e) => e.event_type.startsWith("TOOL_CALL_") || e.event_type in PIPELINE_EVENT_TITLE).slice(-8);
  const pipelineStarted = jobs.length > 0 || events.some((e) => ["RUN_STARTED", "RUN_RETRIED", "DEFINITION_RESOLVED", "EVIDENCE_FOUND", "CALCULATION_COMPLETED", "RECALCULATION_COMPLETED", "REVIEW_REQUIRED", "RUN_COMPLETED", "RUN_FAILED"].includes(e.event_type));
  const reviewVisible = open > 0;
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
      <div id="card-case"><TaskCard title={!pipelineStarted ? snapshot?.documents.length ? "Waiting for required documents" : "Ready for document intake" : active ? "Covenant review in progress" : "Covenant review record"} active={active} steps={[
          { label: "Document intake", state: snapshot?.documents.length ? "done" : active ? "active" : "pending" },
          { label: "Agreement and amendment resolution", state: rules.length ? "done" : active ? "active" : "pending" },
          { label: "Evidence mapping", state: calc ? "done" : active ? "active" : "pending" },
          { label: "Deterministic calculation", state: calc ? "done" : active ? "active" : "pending" },
        ]} /></div>
      {snapshot && snapshot.documents.length > 0 && <div id="card-documents"><ArtifactCard title={`${snapshot.documents.length} source document${snapshot.documents.length === 1 ? "" : "s"}`} subtitle={uploaded ? uploaded.job_id ? `Attached to ${uploaded.revision_id} · background job ${short(uploaded.job_id)}` : `Registered on ${uploaded.revision_id} · the agent will decide the next valid tool` : "Authorized source files form the immutable evidence record."}>
          <div className={s.documentGrid}>{snapshot.documents.map((document) => { const id = docId(document); const meta = documentMeta[id] ?? { document_id: id }; return <button type="button" className={s.documentCard} key={id} onClick={() => onPreviewDocument(meta)}><span className={s.documentIcon}>{meta.media_type === "application/pdf" ? "PDF" : "DOC"}</span><span><strong>{meta.title ?? `Source ${short(id)}`}</strong><small>{roleName(meta.document_role)} · version {meta.version_number ?? 1} · {bytes(meta.byte_size)}</small><code>{short(meta.sha256 ?? id)}</code></span><b>Preview</b></button>; })}</div>
        </ArtifactCard></div>}
      {pipelineStarted && <>
        {jobs.slice(-3).reverse().map((job) => <ToolCard key={job.job_id} title="Run deterministic controls" state={job.state === "failed" ? "error" : job.state === "completed" ? "complete" : job.state === "queued" ? "queued" : "running"} summary={job.state === "failed" ? "Control run needs a retry" : `Revision ${job.revision_id} · attempt ${job.attempt_count}`} output={<p>{job.state === "failed" ? "Retry the calculation. Technical logs are kept in case history." : TERMINAL_JOB_STATES.has(job.state) ? "Control stage finished." : "Processing in the background."}</p>} />)}
        {toolEvents.map((event) => {
          const historicalStart = event.event_type.endsWith("STARTED") && (!active || (event.event_type === "CALCULATION_STARTED" && Boolean(calc)));
          const state = event.event_type.endsWith("FAILED") ? "error" : event.event_type.endsWith("STARTED") && !historicalStart ? "running" : "complete";
          const anchor = event.event_type === "AGREEMENT_RESOLVED" ? "card-agreement" : event.event_type === "DEFINITIONS_COMPILED" ? "card-definitions" : event.event_type === "EVIDENCE_MAPPED" ? "card-evidence" : undefined;
          return <ToolCard id={anchor} key={event.sequence} title={PIPELINE_EVENT_TITLE[event.event_type] ?? String(event.payload?.tool_name ?? "Covenant agent tool")} state={state} summary={eventSummary(event).replace(/undefined/g, "current revision")} input={<code>Revision {event.revision_id ?? snapshot?.revision.revision_id ?? "current"}</code>} output={<p>{eventSummary(event).replace(/undefined/g, "current revision")}</p>} />;
        })}
      </>}
      {calc && <div id="card-calculation"><ArtifactCard title="Covenant calculation" subtitle="The formula is deterministic. The source interpretation and mapped evidence stay reviewable.">
        <div className={`${s.resultBanner} ${calc.period_check?.matches === false ? s.resultNeedsReview : calculationPasses(Number(calc.ratio), calc.comparator, Number(calc.threshold)) ? s.resultPass : s.resultFail}`}><span>{calc.period_check?.matches === false ? "Period review required" : calculationPasses(Number(calc.ratio), calc.comparator, Number(calc.threshold)) ? "Within contractual limit" : "Outside contractual limit"}</span><strong>{calc.ratio}× {calc.comparator} {calc.threshold}×</strong><p>{calc.period_check?.matches === false ? (calc.period_check.note ?? `The financial period ${calc.period_check.facts_period_end} does not match the test period ${calc.period_check.measurement_period_end}.`) : calculationPasses(Number(calc.ratio), calc.comparator, Number(calc.threshold)) ? `${Math.abs(Number(calc.threshold) - Number(calc.ratio)).toFixed(2)}× headroom remains before the limit.` : `The ratio is outside the limit by ${Math.abs(Number(calc.ratio) - Number(calc.threshold)).toFixed(2)}×.`}</p></div>
        <div className={s.calculationGrid}><div><span>Calculated ratio</span><strong>{calc.ratio}×</strong><small>Result produced by Decimal arithmetic.</small></div><div><span>Contractual test</span><strong>{calc.comparator} {calc.threshold}×</strong><small>Limit extracted from the cited agreement.</small></div><div className={s.calculationWide}><span>Calculation inputs</span><div className={s.inputGrid}>{Object.entries(calc.inputs).map(([key, value]) => <span key={key}><code>{key.replaceAll("_", " ")}</code><strong>{value}</strong></span>)}</div></div><div className={s.calculationWide}><span>Governing sources</span><p>{rules.length ? "Open a cited rule to inspect the contractual basis used for this result." : "No cited rule is available for this revision."}</p>{rules.slice(0, 3).map((rule) => <button key={rule.external_rule_id} type="button" className={s.citeButton} onClick={() => onSelectSource(rule.external_rule_id)}>{rule.external_rule_id}</button>)}</div></div>
      </ArtifactCard></div>}
      {rules.length > 0 && <div id="card-definitions"><ArtifactCard title="Covenant definitions" subtitle="Contract terms extracted from the governing agreement and retained with source support."><div className={s.evidenceTable} role="table" aria-label="Covenant definitions"><div role="row"><strong role="columnheader">Definition</strong><strong role="columnheader">Contract test</strong></div>{rules.map((rule) => <button type="button" role="row" key={rule.external_rule_id} onClick={() => onSelectSource(rule.external_rule_id)}><span role="cell"><b>{rule.external_rule_id}</b><small>{rule.covenant_type.replaceAll("_", " ")}</small></span><span role="cell"><code>{rule.comparator} {rule.threshold}</code><small>{rule.support_state}</small></span></button>)}</div></ArtifactCard></div>}
      {facts.length > 0 && <div id="card-evidence"><ArtifactCard title="Mapped financial evidence" subtitle="Each amount is tied to the reporting period and evidence state used by the calculation."><div className={s.evidenceTable} role="table" aria-label="Mapped financial evidence"><div role="row"><strong role="columnheader">Financial fact</strong><strong role="columnheader">Mapped value</strong></div>{facts.map((fact) => <div role="row" key={`${fact.fact_key}-${fact.period_end}`}><span role="cell"><b>{fact.fact_key.replaceAll("_", " ")}</b><small>Period ending {fact.period_end}</small></span><span role="cell"><code>{fact.amount} {fact.currency}</code><small>{fact.evidence_state}</small></span></div>)}</div></ArtifactCard></div>}
      {snapshot && reviewVisible && <div id="card-review"><ConfirmationCard state="required" title="A controller decision is required" detail="Evidence validation found a condition that requires human judgment. The agent has paused and nothing was assumed or defaulted."><Gated allowed={mutate} needed="treasury_reviewer, officer or admin" label="Review decisions are disabled."><ReviewInbox caseId={caseId} snapshot={snapshot} onChange={refresh} /></Gated></ConfirmationCard></div>}
      {lastResolved != null && <ConfirmationCard state="resolved" title={PHASE_LABEL[phase]} detail="The decision is bound to this revision. Recalculation must finish before approval."><TaskCard title="Recheck current revision" active={phase !== "ready"} steps={(["recorded", "recalculating", "rechecked", "ready"] as const).map((step, index) => ({ label: PHASE_LABEL[step], state: index < ["recorded", "recalculating", "rechecked", "ready"].indexOf(phase) ? "done" : step === phase ? "active" : "pending" }))} /></ConfirmationCard>}
      {snapshot && revisionVisible && <details className={s.collapsedAction}><summary>Revision history and amendment controls</summary><Gated allowed={mutate} needed="treasury_reviewer, officer or admin" label="Amendment recording is disabled."><RevisionPanel caseId={caseId} snapshot={snapshot} revisions={revisions} onChange={refresh} /></Gated></details>}
      {snapshot && (snapshot.package_state === "ready_for_officer_review" || snapshot.package_state === "approved_draft") && <div id="card-package"><ArtifactCard title="Draft ready for officer review" subtitle="This is an internally approved draft, never an e-signature or lender delivery."><Gated allowed={canApprove(role)} needed="officer or admin" label="Approval is disabled."><OfficerApproval caseId={caseId} snapshot={snapshot} result={null} role={role} approval={locked} onApproved={setLocked} onChange={refresh} /></Gated><DownloadPackage info={null} snapshot={snapshot} result={null} approval={locked} /></ArtifactCard></div>}

    </>
  );
}
