"use client";

import { useCallback, useEffect, useState } from "react";
import { CopilotChat } from "@copilotkit/react-core/v2";
import styles from "./page.module.css";

type CaseSummary = { id: string; name: string; narrative: string; agreement: string; agreement_version: string; test_date: string; scenario_type: string };
type Result = {
  status: "DRAFT_COMPLIANT" | "DRAFT_BREACH" | "NEEDS_REVIEW";
  status_reason: string;
  case: CaseSummary;
  calculation: { formula: string; numerator: number; denominator: number; ratio: number; threshold: number; comparator: string; headroom: number; original_threshold?: number | null };
  citations: { document: string; locator: string; excerpt: string }[];
  evidence: { label: string; value: string; source: string; supported: boolean }[];
  blocking_issues: string[];
  trace: { step: string; label: string; detail: string }[];
  certificate: { draft_mark: string; agreement: string; agreement_version: string; test_date: string; result: string; finalization_allowed: boolean; generated_at: string };
};

const fallbackCases: CaseSummary[] = [
  { id: "aurora-net-leverage", name: "Aurora: net leverage passes", narrative: "Cash netting and lease treatment lead to a compliant draft.", agreement: "Aurora Credit Agreement", agreement_version: "Original agreement", test_date: "2026-06-30", scenario_type: "comparison" },
  { id: "beacon-gross-leverage", name: "Beacon: gross leverage breaches", narrative: "Same financials, different agreement, opposite verdict.", agreement: "Beacon Term Loan Agreement", agreement_version: "Original agreement", test_date: "2026-06-30", scenario_type: "comparison" },
  { id: "beacon-amendment", name: "Beacon: amendment controls", narrative: "A time-bound amendment changes the applicable threshold.", agreement: "Beacon Term Loan Agreement", agreement_version: "Amendment No. 2 (controlling)", test_date: "2026-06-30", scenario_type: "amendment" },
  { id: "meridian-evidence-gap", name: "Meridian: evidence gap requires review", narrative: "Missing add-back support blocks a compliance conclusion.", agreement: "Meridian Revolving Credit Agreement", agreement_version: "Amendment No. 1", test_date: "2026-06-30", scenario_type: "evidence_gap" },
];

const labelFor = (status: Result["status"]) => status === "DRAFT_COMPLIANT" ? "Draft compliant" : status === "DRAFT_BREACH" ? "Draft breach" : "Needs review";
const number = (value: number) => `$${value.toLocaleString("en-US", { maximumFractionDigits: 2 })}m`;

export default function HomePage() {
  const [cases, setCases] = useState<CaseSummary[]>(fallbackCases);
  const [selected, setSelected] = useState(fallbackCases[0].id);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/covenant/demo-cases").then((r) => r.ok ? r.json() : Promise.reject()).then(setCases).catch(() => setError("API is offline — start the API service to run the live workflow."));
  }, []);

  const run = useCallback(async (decision = "pending") => {
    setLoading(true); setError("");
    try {
      const reviewerRationale = decision === "approve_addback"
        ? "Management support reviewed and reconciled for the demo."
        : decision === "reject_addback"
          ? "Requested supporting evidence was not delivered."
          : null;
      const response = await fetch(`/api/covenant/cases/${selected}/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reviewer_decision: decision, reviewer_name: decision === "pending" ? null : "Treasury reviewer", reviewer_rationale: reviewerRationale }) });
      if (!response.ok) throw new Error("The workflow could not be run.");
      setResult(await response.json());
    } catch (err) { setError(err instanceof Error ? err.message : "The workflow could not be run."); }
    finally { setLoading(false); }
  }, [selected]);

  const download = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result.certificate, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `covenant-certificate-${result.case.id}.json`; anchor.click(); URL.revokeObjectURL(url);
  };

  const active = cases.find((item) => item.id === selected) ?? fallbackCases[0];
  const statusClass = result?.status === "DRAFT_COMPLIANT" ? styles.good : result?.status === "DRAFT_BREACH" ? styles.bad : styles.review;

  return <main className={styles.shell}>
    <nav className={styles.nav}>
      <a className={styles.brand} href="#top"><span className={styles.brandMark}>C</span><span>Covenant <b>Certificate</b></span></a>
      <div className={styles.navMeta}><span className={styles.liveDot} /> Treasury control room <span className={styles.divider} /> Q2 2026</div>
    </nav>

    <section id="top" className={styles.hero}>
      <div><p className={styles.eyebrow}>AUTONOMOUS OFFICE OF THE CFO</p><h1>Know the covenant<br /><em>before</em> you sign.</h1><p className={styles.subhead}>A reviewable workflow that turns agreement language and financial evidence into a cited, deterministic draft certificate.</p></div>
      <div className={styles.heroCard}><span className={styles.cardKicker}>CONTROL PRINCIPLE</span><strong>Never certify what<br />you cannot prove.</strong><p>Uncertain clauses, missing evidence, and unresolved amendments stop the workflow — they never become a silent pass.</p></div>
    </section>

    <section className={styles.workflow}>
      <div className={styles.sectionHead}><div><p className={styles.eyebrow}>DEMO WORKFLOW</p><h2>Run a covenant case</h2></div><p>Choose a scenario, then inspect the clause-to-calculation evidence trail.</p></div>
      <div className={styles.caseGrid}>{cases.map((item, index) => <button key={item.id} onClick={() => { setSelected(item.id); setResult(null); }} className={`${styles.caseCard} ${selected === item.id ? styles.selected : ""}`}><span>0{index + 1} · {item.scenario_type.replace("_", " ")}</span><strong>{item.name}</strong><small>{item.narrative}</small></button>)}</div>
      <div className={styles.runBar}><div><span className={styles.runAgreement}>{active.agreement}</span><span>{active.agreement_version} · Test date {active.test_date}</span></div><button className={styles.runButton} onClick={() => run()} disabled={loading}>{loading ? "Running controls…" : "Run evidence-first workflow →"}</button></div>
      {error && <p className={styles.error}>{error}</p>}
    </section>

    {result ? <section className={styles.resultSection}>
      <div className={styles.resultTop}><div><p className={styles.eyebrow}>DRAFT RESULT</p><h2>{result.case.name}</h2></div><div className={`${styles.status} ${statusClass}`}><span>{labelFor(result.status)}</span><b>{result.calculation.ratio.toFixed(2)}x</b><small>{result.calculation.comparator} {result.calculation.threshold.toFixed(2)}x</small></div></div>
      <p className={styles.reason}>{result.status_reason}</p>
      <div className={styles.dataGrid}>
        <article className={styles.calcCard}><p className={styles.cardKicker}>DETERMINISTIC CALCULATION</p><code>{result.calculation.formula}</code><div className={styles.math}><div><small>Numerator</small><strong>{number(result.calculation.numerator)}</strong></div><span>÷</span><div><small>Denominator</small><strong>{number(result.calculation.denominator)}</strong></div><span>=</span><div><small>Ratio</small><strong>{result.calculation.ratio.toFixed(2)}x</strong></div></div><div className={styles.headroom}>Headroom <b>{result.calculation.headroom >= 0 ? "+" : ""}{result.calculation.headroom.toFixed(2)}x</b>{result.calculation.original_threshold ? <span> Original threshold <s>{result.calculation.original_threshold.toFixed(2)}x</s></span> : null}</div></article>
        <article className={styles.certificate}><p className={styles.cardKicker}>CERTIFICATE STATE</p><strong>{result.certificate.draft_mark}</strong><p>{result.certificate.agreement}<br />{result.certificate.agreement_version}</p><button onClick={download} disabled={!result.certificate.finalization_allowed}>Download draft evidence</button></article>
      </div>
      {result.blocking_issues.length > 0 && <article className={styles.blocker}><div><p className={styles.cardKicker}>HUMAN DECISION REQUIRED</p><strong>{result.blocking_issues[0]}</strong></div><div><button onClick={() => run("approve_addback")}>Evidence approved</button><button className={styles.reject} onClick={() => run("reject_addback")}>Reject add-back</button></div></article>}
      <div className={styles.detailGrid}>
        <article><p className={styles.cardKicker}>EVIDENCE MAPPING</p>{result.evidence.map((fact) => <div key={fact.label} className={styles.evidence}><span className={fact.supported ? styles.check : styles.missing}>{fact.supported ? "✓" : "!"}</span><div><strong>{fact.label} <b>{fact.value}</b></strong><small>{fact.source}</small></div></div>)}</article>
        <article><p className={styles.cardKicker}>CITED CONTRACT TERMS</p>{result.citations.map((citation) => <div key={citation.locator} className={styles.citation}><span>{citation.locator}</span><strong>{citation.document}</strong><p>“{citation.excerpt}”</p></div>)}</article>
      </div>
      <article className={styles.trace}><p className={styles.cardKicker}>AUDITABLE WORKFLOW TRACE</p>{result.trace.map((event) => <div key={event.step}><span>{event.step}</span><strong>{event.label}</strong><p>{event.detail}</p></div>)}</article>
    </section> : <section className={styles.empty}><span>01 → 05</span><h2>Every verdict has a spine.</h2><p>Resolve the controlling agreement. Cite the term. Map the evidence. Calculate in code. Escalate what a system cannot safely decide.</p></section>}
    <section className={styles.agentSection}>
      <div className={styles.agentIntro}><p className={styles.eyebrow}>LANGGRAPH · AG-UI</p><h2>Ask the treasury copilot</h2><p>The agent can explain or run the curated cases, but every ratio and verdict still comes from the deterministic Python control layer.</p></div>
      <div className={styles.agentChat}><CopilotChat labels={{ welcomeMessageText: "Ask me to list the cases, or run one using its case ID.", chatInputPlaceholder: "Ask about a covenant case..." }} /></div>
    </section>
    <footer className={styles.footer}><span>Covenant Certificate</span><span>Drafting support only · Authorized officer approval required</span></footer>
  </main>;
}
