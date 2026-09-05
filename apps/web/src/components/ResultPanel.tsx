"use client";

import { fix, num, Num, RunResult, Snapshot } from "@/lib/api";
import styles from "@/app/page.module.css";

const labelFor = (status: RunResult["status"]) => status === "DRAFT_COMPLIANT" ? "Draft compliant" : status === "DRAFT_BREACH" ? "Draft breach" : "Needs review";
const money = (value: Num) => `$${num(value).toLocaleString("en-US", { maximumFractionDigits: 2 })}m`;

function Json({ label, value }: { label: string; value: unknown }) {
  if (value == null) return null;
  return <details className={styles.details}><summary>{label}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
}

export function ResultPanel({ result, snapshot }: { result: RunResult | null; snapshot: Snapshot | null }) {
  const extras = <>
    <Json label="Pipeline artifacts" value={snapshot?.artifacts} />
    <Json label="Financial facts" value={snapshot?.financial_facts} />
    <Json label="Covenant rules" value={snapshot?.covenant_rules} />
  </>;
  if (!result) return <section className={styles.resultSection}>
    <p className={styles.eyebrow}>3 · RESULT</p>
    <p className={styles.muted}>No calculation yet — press <b>Recalculate</b> to run the deterministic control layer for this case.</p>
    {extras}
  </section>;

  const statusClass = result.status === "DRAFT_COMPLIANT" ? styles.good : result.status === "DRAFT_BREACH" ? styles.bad : styles.review;
  const { calculation } = result;
  return <section className={styles.resultSection} aria-live="polite">
    <div className={styles.resultTop}>
      <div><p className={styles.eyebrow}>3 · DRAFT RESULT{result.run_id ? ` · run ${result.run_id}` : ""}</p><h2>{result.case.name}</h2></div>
      <div className={`${styles.status} ${statusClass}`}><span>{labelFor(result.status)}</span><b>{fix(calculation.ratio)}x</b><small>{calculation.comparator} {fix(calculation.threshold)}x</small></div>
    </div>
    <p className={styles.reason}>{result.status_reason}</p>
    <div className={styles.dataGrid}>
      <article className={styles.calcCard}>
        <p className={styles.cardKicker}>DETERMINISTIC CALCULATION</p>
        <code>{calculation.formula}</code>
        <div className={styles.math}>
          <div><small>Numerator</small><strong>{money(calculation.numerator)}</strong></div><span aria-hidden="true">÷</span>
          <div><small>Denominator</small><strong>{money(calculation.denominator)}</strong></div><span aria-hidden="true">=</span>
          <div><small>Ratio</small><strong>{fix(calculation.ratio)}x</strong></div>
        </div>
        <div className={styles.headroom}>Headroom <b>{num(calculation.headroom) >= 0 ? "+" : ""}{fix(calculation.headroom)}x</b>{calculation.original_threshold ? <span> Original threshold <s>{fix(calculation.original_threshold)}x</s></span> : null}</div>
      </article>
      <article className={styles.certificate}>
        <p className={styles.cardKicker}>CERTIFICATE STATE</p>
        <strong>{result.certificate.draft_mark}</strong>
        <p>{result.certificate.agreement}<br />{result.certificate.agreement_version}</p>
        <span className={styles.muted}>Finalization allowed: {result.certificate.finalization_allowed ? "yes" : "no"} · generated {result.certificate.generated_at}</span>
      </article>
    </div>
    {result.blocking_issues.length > 0 && <article className={styles.blocker}>
      <div><p className={styles.cardKicker}>HUMAN DECISION REQUIRED</p>{result.blocking_issues.map((issue) => <strong key={issue}>{issue}</strong>)}</div>
      <p className={styles.muted}>Resolve it in the review inbox below — decisions are recorded against the revision, not replayed.</p>
    </article>}
    <div className={styles.detailGrid}>
      <article><p className={styles.cardKicker}>EVIDENCE MAPPING</p>{result.evidence.map((fact) => <div key={fact.label} className={styles.evidence}><span className={fact.supported ? styles.check : styles.missing} role="img" aria-label={fact.supported ? "supported" : "unsupported"}>{fact.supported ? "✓" : "!"}</span><div><strong>{fact.label} <b>{fact.value}</b></strong><small>{fact.source}</small></div></div>)}</article>
      <article><p className={styles.cardKicker}>CITED CONTRACT TERMS</p>{result.citations.map((citation) => <div key={citation.locator} className={styles.citation}><span>{citation.locator}</span><strong>{citation.document}</strong><p>“{citation.excerpt}”</p></div>)}</article>
    </div>
    <article className={styles.trace}><p className={styles.visuallyHidden}>Auditable workflow trace</p>{result.trace.map((event) => <div key={event.step}><span>{event.step}</span><strong>{event.label}</strong><p>{event.detail}</p></div>)}</article>
    {extras}
    <Json label="Per-covenant results (from /run)" value={result.covenant_results} />
    <Json label="Coverage (from /run)" value={result.coverage} />
  </section>;
}
