"use client";

import { Job, post, TERMINAL_JOB_STATES, useAction } from "@/lib/api";
import styles from "@/app/page.module.css";

const chip = (state: string) => state === "completed" ? styles.chipGood : state === "failed" ? styles.chipBad : state === "running" ? styles.chipWarn : styles.chipNeutral;

export function JobTimeline({ jobs, polling, onChange }: { jobs: Job[]; polling: boolean; onChange: () => Promise<void> }) {
  const { run, error } = useAction(onChange);
  return <article className={styles.panel}>
    <p className={styles.cardKicker}>2 · JOB TIMELINE {polling ? "· polling every 2 s" : ""}</p>
    <h3>Durable worker jobs</h3>
    <div aria-live="polite">
      {jobs.length === 0 && <p className={styles.muted}>No jobs yet — an upload enqueues one. (Offline API without an in-process worker: jobs stay <code>queued</code>.)</p>}
      {jobs.map((job) => <div key={job.job_id} className={styles.row}>
        <span className={`${styles.chip} ${chip(job.state)}`}>{job.state}</span>
        <code>{job.job_id}</code>
        <span>{job.revision_id} · attempt {job.attempt_count}{job.lease_owner ? ` · lease ${job.lease_owner}` : ""}</span>
        {job.last_error && <small className={styles.error}>{job.last_error}</small>}
        {!TERMINAL_JOB_STATES.has(job.state) && <button type="button" className={styles.secondaryButton} onClick={() => run(async () => { await post(`/jobs/${job.job_id}/cancel`, {}); await onChange(); })}>Cancel</button>}
      </div>)}
    </div>
    <p role="alert" aria-live="polite" className={styles.error}>{error}</p>
  </article>;
}
