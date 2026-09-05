"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CopilotChat } from "@copilotkit/react-core/v2";
import { api, CaseSummary } from "@/lib/api";
import { SignIn } from "@/components/SignIn";
import styles from "./page.module.css";

export default function HomePage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<CaseSummary[]>("/demo-cases").then(setCases).catch((err: Error) => setError(`${err.message} — start the API service to load the cases.`));
  }, []);

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
      <div className={styles.sectionHead}>
        <div><p className={styles.eyebrow}>DEMO WORKFLOW</p><h2>Open a covenant case</h2><p>Upload evidence, watch the worker, resolve the review pause, record an amendment, approve the exact draft.</p></div>
        <SignIn />
      </div>
      <p role="alert" aria-live="polite" className={styles.error}>{error}</p>
      <div className={styles.caseGrid} aria-busy={!cases.length && !error}>
        {cases.map((item, index) => <Link key={item.id} href={`/cases/${item.id}`} className={styles.caseCard}>
          <span>0{index + 1} · {item.scenario_type.replace("_", " ")}</span>
          <strong>{item.name}</strong>
          <small>{item.narrative}</small>
          {item.scenario_type === "comparison" && <em className={styles.hypo}>Labelled hypothetical</em>}
        </Link>)}
      </div>
      <p className={styles.muted}>Two-agreement comparisons (Aurora vs Beacon) use synthetic agreements over one financial packet: a labelled hypothetical, not a claim about any issuer&apos;s actual compliance.</p>
    </section>

    <section className={styles.empty}><span>01 → 07</span><h2>Every verdict has a spine.</h2><p>Resolve the controlling agreement. Cite the term. Map the evidence. Calculate in code. Escalate what a system cannot safely decide. Approve the exact draft.</p></section>

    <section className={styles.agentSection}>
      <div className={styles.agentIntro}><p className={styles.eyebrow}>LANGGRAPH · AG-UI</p><h2>Ask the treasury copilot</h2><p>The agent can explain or run the curated cases, but every ratio and verdict still comes from the deterministic Python control layer.</p></div>
      <div className={styles.agentChat}><CopilotChat labels={{ welcomeMessageText: "Ask me to list the cases, or run one using its case ID.", chatInputPlaceholder: "Ask about a covenant case..." }} /></div>
    </section>
    <footer className={styles.footer}><span>Covenant Certificate</span><span>Drafting support only · Authorized officer approval required</span></footer>
  </main>;
}
