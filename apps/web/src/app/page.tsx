"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { CopilotChat } from "@copilotkit/react-core/v2";
import { api, CaseListItem, CaseSummary, createCase, listCases, useAction, useIdentity } from "@/lib/api";
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
      <NewCase templates={cases} />
      <p className={styles.eyebrow}>CURATED TEMPLATES</p>
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

/** Start a fresh case from a catalog template (reviewer+), then list the caller's org cases. */
function NewCase({ templates }: { templates: CaseSummary[] }) {
  const router = useRouter();
  const identity = useIdentity();
  const { run, busy, error } = useAction();
  const [mine, setMine] = useState<CaseListItem[] | null>(null); // null = not allowed / not loaded → render nothing

  useEffect(() => { listCases().then(setMine).catch(() => setMine(null)); }, [identity.kind, identity.label]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    run(async () => {
      const created = await createCase({
        template_case_id: String(form.get("template_case_id")),
        name: String(form.get("name") ?? "").trim() || undefined,
        test_date: String(form.get("test_date") ?? "") || undefined,
      });
      router.push(`/cases/${created.case_id}`);
    });
  };

  return <>
    <article className={styles.panel}>
      <p className={styles.cardKicker}>START A NEW CASE</p>
      <h3>Fresh case from a template</h3>
      <form onSubmit={submit} className={styles.form}>
        <div className={styles.inline}>
          <label>Template <select name="template_case_id" required defaultValue="aon-term-loan-leverage">{templates.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Case name <input name="name" maxLength={240} placeholder="e.g. Aon Q1 2024 review" /></label>
          <label>Test date (optional) <input name="test_date" type="date" /></label>
        </div>
        <button disabled={busy || !templates.length}>{busy ? "Creating…" : "Create case → open workbench"}</button>
      </form>
      <p role="alert" aria-live="polite" className={styles.error}>{error}</p>
      <p className={styles.muted}>Reviewer or officer role required. The new case starts at rev-1 with the template&apos;s covenant rule; uploads and revisions stay on it, so the seeded cases stay clean.</p>
    </article>
    {mine && <>
      <p className={styles.eyebrow}>YOUR CASES · {identity.label}</p>
      {mine.length ? <div className={styles.caseGrid}>
        {mine.map((item) => <Link key={item.case_id} href={`/cases/${item.case_id}`} className={styles.caseCard}>
          <span>{item.run_state ?? "—"}{item.template_case_id && ` · from ${item.template_case_id}`}</span>
          <strong>{item.name}</strong>
          <small><code>{item.case_id}</code>{item.created_at && ` · created ${item.created_at.slice(0, 10)}`}</small>
        </Link>)}
      </div> : <p className={styles.muted}>No cases yet for this identity — create one above.</p>}
    </>}
  </>;
}
