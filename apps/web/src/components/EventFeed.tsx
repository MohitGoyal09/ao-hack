"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, useIdentity } from "@/lib/api";
import styles from "@/app/page.module.css";

// GET /api/cases/{id}/events — durable domain_events rows; payload is ids/hashes only, never document text.
export type DomainEvent = { sequence: number; event_type: string; revision_id: string | null; run_id: string | null; payload: Record<string, unknown>; created_at: string | null };

const SUMMARY: Record<string, (p: Record<string, unknown>) => string> = {
  REVISION_CREATED: () => "Revision opened — inputs hashed and locked",
  DOCUMENT_UPLOADED: (p) => `Document ${p.document_id} v${p.version} accepted as an immutable version`,
  RUN_STARTED: (p) => `Worker leased job ${p.job_id}`,
  RUN_RETRIED: (p) => `Job ${p.job_id} retried (attempt ${p.attempt})${p.last_error ? ` — ${p.last_error}` : ""}`,
  CALCULATION_COMPLETED: (p) => `Deterministic calculation stored — ratio ${p.ratio} against threshold ${p.threshold}`,
  REVIEW_REQUIRED: (p) => `Human review required — extraction ${p.extraction_state}; nothing defaulted to zero`,
  RUN_COMPLETED: (p) => `Run finished: ${p.status}`,
  INPUT_CHANGED: () => "Amendment recorded — inputs changed",
  RESULT_INVALIDATED: () => "Prior results marked stale",
  REVIEW_RESOLVED: () => "Review decision recorded",
  APPROVAL_RECORDED: () => "Officer approval locked the exact numbers",
};
const summary = (e: DomainEvent) => (SUMMARY[e.event_type] ?? (() => e.event_type))(e.payload ?? {});
const tone = (e: DomainEvent) => {
  if (e.event_type === "RUN_COMPLETED") return e.payload?.status === "completed" ? styles.chipGood : styles.chipWarn;
  if (["CALCULATION_COMPLETED", "APPROVAL_RECORDED"].includes(e.event_type)) return styles.chipGood;
  if (["REVIEW_REQUIRED", "RUN_RETRIED", "RESULT_INVALIDATED"].includes(e.event_type)) return styles.chipWarn;
  return styles.chipNeutral;
};

/** Live pipeline activity: cursor-polls `after_sequence` (2 s while a job runs, else 10 s), newest first. */
export function EventFeed({ caseId, polling }: { caseId: string; polling: boolean }) {
  const identity = useIdentity();
  const [events, setEvents] = useState<DomainEvent[]>([]);
  const [error, setError] = useState("");
  const seen = useRef<DomainEvent[]>([]);
  const tick = useCallback(async () => {
    const have = seen.current;
    const after = have.length ? have[have.length - 1].sequence : 0;
    try {
      const fresh = await api<DomainEvent[]>(`/cases/${caseId}/events?after_sequence=${after}&limit=200`);
      if (seen.current !== have) return; // a reset or an earlier tick landed first; drop this batch
      if (fresh.length) { seen.current = [...have, ...fresh]; setEvents(seen.current); }
      setError("");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }, [caseId]);
  const who = `${identity.kind}:${identity.label}:${identity.role}`;
  useEffect(() => { seen.current = []; setEvents([]); tick(); }, [tick, who]); // case or bearer changed → restart the cursor
  useEffect(() => { const timer = setInterval(tick, polling ? 2000 : 10000); return () => clearInterval(timer); }, [tick, polling]);

  return <article className={styles.panel}>
    <p className={styles.cardKicker}>2b · PIPELINE ACTIVITY · {polling ? "live, every 2 s" : "every 10 s"}</p>
    <h3>Durable domain events</h3>
    <p className={styles.muted}>Append-only <code>domain_events</code> written by the API and the worker — identifiers and hashes only, never document text. Newest first.</p>
    <ol className={styles.feed} aria-live="polite">
      {events.length === 0 && <li className={styles.muted}>No events yet — the first snapshot read creates the revision; an upload starts a run.</li>}
      {[...events].reverse().map((e) => <li key={e.sequence} className={styles.row}>
        <span className={styles.feedTime}>#{e.sequence}{e.created_at ? ` · ${new Date(e.created_at).toLocaleTimeString()}` : ""}</span>
        <span className={`${styles.chip} ${tone(e)}`}>{e.event_type}</span>
        {e.revision_id && <code>{e.revision_id}</code>}
        <span>{summary(e)}</span>
      </li>)}
    </ol>
    <p role="alert" aria-live="polite" className={styles.error}>{error}</p>
  </article>;
}
