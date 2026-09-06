"use client";

import type { ReactNode } from "react";
import s from "./workflow-cards.module.css";

type ToolState = "running" | "complete" | "error" | "queued";

const toolLabel: Record<ToolState, string> = {
  running: "Running",
  complete: "Complete",
  error: "Needs attention",
  queued: "Queued",
};

export function ToolCard({ title, state, summary, input, output }: { title: string; state: ToolState; summary: string; input?: ReactNode; output?: ReactNode }) {
  return <details className={s.tool} open={state === "running" || state === "error"}>
    <summary>
      <span className={`${s.dot} ${s[`dot${state[0].toUpperCase()}${state.slice(1)}`]}`} aria-hidden="true" />
      <span className={s.toolTitle}>{title}</span>
      <span className={s.toolSummary}>{summary}</span>
      <span className={s.state}>{toolLabel[state]}</span>
    </summary>
    {(input || output) && <div className={s.toolBody}>
      {input && <div><span className={s.label}>Input</span>{input}</div>}
      {output && <div><span className={s.label}>Output</span>{output}</div>}
    </div>}
  </details>;
}

export function TaskCard({ title, steps, active }: { title: string; steps: { label: string; state: "done" | "active" | "pending" }[]; active?: boolean }) {
  const allDone = steps.every((step) => step.state === "done");
  const stateLabel = active ? "Processing" : allDone ? "Complete" : "Ready";
  return <section className={s.task} aria-label={title}>
    <div className={s.taskHead}><div><span className={s.eyebrow}>Agent workflow</span><h3>{title}</h3></div><span className={active ? s.live : s.quiet}>{stateLabel}</span></div>
    <ol>{steps.map((step) => <li key={step.label} className={s[`step${step.state[0].toUpperCase()}${step.state.slice(1)}`]}><span aria-hidden="true">{step.state === "done" ? "✓" : step.state === "active" ? "•" : "○"}</span>{step.label}</li>)}</ol>
  </section>;
}

export function ArtifactCard({ title, subtitle, children, actions }: { title: string; subtitle: string; children: ReactNode; actions?: ReactNode }) {
  return <section className={s.artifact} aria-label={title}>
    <header><div><span className={s.eyebrow}>Verified artifact</span><h3>{title}</h3><p>{subtitle}</p></div><span className={s.artifactMark}>⌁</span></header>
    <div className={s.artifactBody}>{children}</div>
    {actions && <footer>{actions}</footer>}
  </section>;
}

export function ConfirmationCard({ state, title, detail, children }: { state: "required" | "resolved"; title: string; detail: string; children?: ReactNode }) {
  return <section className={s.confirmation} aria-label={title}>
    <div className={s.confirmationHead}><span className={state === "resolved" ? s.check : s.question}>{state === "resolved" ? "✓" : "?"}</span><div><span className={s.eyebrow}>{state === "resolved" ? "Review recorded" : "Controller decision required"}</span><h3>{title}</h3><p>{detail}</p></div></div>
    {children && <div className={s.confirmationBody}>{children}</div>}
  </section>;
}
