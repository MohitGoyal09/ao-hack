"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { api, Approval, CaseSummary, Job, post, Revision, RunResult, Snapshot, TERMINAL_JOB_STATES, useAction, useIdentity } from "@/lib/api";
import { SignIn } from "@/components/SignIn";
import { UploadDocument } from "@/components/UploadDocument";
import { JobTimeline } from "@/components/JobTimeline";
import { EventFeed } from "@/components/EventFeed";
import { ResultPanel } from "@/components/ResultPanel";
import { ReviewInbox } from "@/components/ReviewInbox";
import { RevisionPanel } from "@/components/RevisionPanel";
import { OfficerApproval } from "@/components/OfficerApproval";
import { DownloadPackage } from "@/components/DownloadPackage";
import styles from "@/app/page.module.css";

export default function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const identity = useIdentity();
  const [info, setInfo] = useState<CaseSummary | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [result, setResult] = useState<RunResult | null>(null);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [error, setError] = useState("");
  const { run: recalc, busy, error: runError } = useAction();

  const refresh = useCallback(async () => {
    try {
      const [snap, jobList] = await Promise.all([api<Snapshot>(`/cases/${id}/snapshot`), api<Job[]>(`/cases/${id}/jobs`)]);
      setSnapshot(snap); setJobs(jobList); setError("");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }, [id]);

  useEffect(() => { api<CaseSummary>(`/cases/${id}`).then(setInfo).catch((err: Error) => setError(err.message)); }, [id]);
  useEffect(() => { refresh(); }, [refresh, identity.kind, identity.label, identity.role]); // identity change → re-read with the new bearer
  useEffect(() => { // the snapshot only carries the head; remember every head we have seen (or use snapshot.revisions when the API sends it)
    if (!snapshot) return;
    if (snapshot.revisions) { setRevisions(snapshot.revisions); return; }
    setRevisions((prev) => prev.some((rev) => rev.revision_id === snapshot.revision.revision_id) ? prev : [...prev, snapshot.revision]);
  }, [snapshot]);
  const polling = jobs.some((job) => !TERMINAL_JOB_STATES.has(job.state)) || snapshot?.run_state === "running";
  useEffect(() => { if (!polling) return; const timer = setInterval(refresh, 2000); return () => clearInterval(timer); }, [polling, refresh]);

  const recalculate = () => recalc(async () => { setResult(await post<RunResult>(`/cases/${id}/run`, {})); await refresh(); });
  const hypothetical = info?.scenario_type === "comparison";

  return <main className={styles.shell}>
    <nav className={styles.nav}>
      <Link className={styles.brand} href="/"><span className={styles.brandMark}>C</span><span>Covenant <b>Certificate</b></span></Link>
      <div className={styles.navMeta}><span className={styles.liveDot} /> {identity.kind === "supabase" ? "Supabase session" : "Offline identity"} <span className={styles.divider} /> {identity.label} · {identity.role}</div>
    </nav>
    <section className={styles.workbench}>
      <div className={styles.sectionHead}>
        <div>
          <p className={styles.eyebrow}>CASE WORKBENCH · {info?.scenario_type.replace("_", " ") ?? id}</p>
          <h2>{info?.name ?? id}</h2>
          {info && <p className={styles.muted}>{info.agreement} · {info.agreement_version} · test date {info.test_date}{info.covenant_name ? ` · ${info.covenant_name}` : ""}</p>}
          {hypothetical && <span className={styles.hypo}>Labelled hypothetical — synthetic agreements, not any issuer&apos;s actual compliance</span>}
        </div>
        <SignIn />
      </div>
      <p role="alert" aria-live="assertive" className={styles.error}>{error}{error.startsWith("401") ? " — sign in or choose an offline identity." : error.startsWith("404") ? " — the case is not visible to this identity's organization." : ""}</p>
      {snapshot && <div className={styles.statusStrip} aria-live="polite">
        <span className={`${styles.chip} ${snapshot.run_state === "completed" ? styles.chipGood : styles.chipWarn}`}>run {snapshot.run_state}</span>
        <span className={`${styles.chip} ${styles.chipNeutral}`}>package {snapshot.package_state}</span>
        <span className={`${styles.chip} ${styles.chipNeutral}`}>head {snapshot.revision.revision_id} · threshold {snapshot.revision.threshold}</span>
        <span className={`${styles.chip} ${snapshot.open_review_issues ? styles.chipWarn : styles.chipGood}`}>{snapshot.open_review_issues} open review issue(s)</span>
        <span className={`${styles.chip} ${styles.chipNeutral}`}>coverage {snapshot.coverage.state}</span>
        <span className={`${styles.chip} ${styles.chipNeutral}`}>{snapshot.documents.length} document(s) · event #{snapshot.last_event_sequence}</span>
        <button type="button" className={styles.runButton} onClick={recalculate} disabled={busy}>{busy ? "Running controls…" : "Recalculate (POST /run)"}</button>
      </div>}
      <p role="alert" aria-live="polite" className={styles.error}>{runError}</p>
      <div className={styles.panelGrid}>
        <UploadDocument caseId={id} onChange={refresh} />
        <JobTimeline jobs={jobs} polling={polling} onChange={refresh} />
      </div>
      <EventFeed caseId={id} polling={polling} />
      <ResultPanel result={result} snapshot={snapshot} />
      {snapshot && <>
        <div className={styles.panelGrid}>
          <ReviewInbox caseId={id} snapshot={snapshot} onChange={refresh} />
          <RevisionPanel caseId={id} snapshot={snapshot} revisions={revisions} onChange={refresh} />
        </div>
        <div className={styles.panelGrid}>
          <OfficerApproval caseId={id} snapshot={snapshot} result={result} role={identity.role} approval={approval} onApproved={setApproval} onChange={refresh} />
          <DownloadPackage info={info} snapshot={snapshot} result={result} approval={approval} />
        </div>
      </>}
    </section>
    <footer className={styles.footer}><span>Covenant Certificate</span><span>Drafting support only · Authorized officer approval required</span></footer>
  </main>;
}
