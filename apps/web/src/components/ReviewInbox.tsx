"use client";

import { FormEvent, useState } from "react";
import { docId, post, ReviewIssue, Snapshot, useAction } from "@/lib/api";
import styles from "@/app/page.module.css";

const DECISIONS = ["accept_evidence", "reject_evidence", "request_document"];
// Until the snapshot carries review_issues[], the store's ids are deterministic: rev-1 seeds `{case}-evidence-1`, later revisions `{case}-{rev}-evidence-1`.
const fallbackIssueId = (caseId: string, revisionId: string) => revisionId === "rev-1" ? `${caseId}-evidence-1` : `${caseId}-${revisionId}-evidence-1`;

export function ReviewInbox({ caseId, snapshot, onChange }: { caseId: string; snapshot: Snapshot; onChange: () => Promise<void> }) {
  const { run, busy, error } = useAction(onChange);
  const [resolved, setResolved] = useState<ReviewIssue[]>([]);
  const issues: ReviewIssue[] = snapshot.review_issues ?? (snapshot.open_review_issues > 0 ? [{ issue_id: fallbackIssueId(caseId, snapshot.revision.revision_id), revision_id: snapshot.revision.revision_id, status: "open" }] : []);
  const open = issues.filter((issue) => issue.status === "open");
  const closed = [...issues.filter((issue) => issue.status !== "open"), ...resolved.filter((r) => !issues.some((i) => i.issue_id === r.issue_id))];

  const submit = (issue: ReviewIssue) => (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    run(async () => {
      const outcome = await post<ReviewIssue>(`/review-issues/${issue.issue_id}/resolve`, {
        revision_id: snapshot.revision.revision_id,
        expected_bundle_hash: snapshot.revision.input_bundle_hash,
        decision_kind: form.get("decision_kind"),
        rationale: form.get("rationale"),
        evidence_refs: form.getAll("evidence_refs"),
        idempotency_key: crypto.randomUUID(),
      });
      setResolved((prev) => [...prev, { ...outcome, rationale: String(form.get("rationale")) }]);
      await onChange();
    });
  };

  return <article className={styles.panel}>
    <p className={styles.cardKicker}>4 · REVIEW INBOX · {snapshot.open_review_issues} open</p>
    <h3>{open.length ? "Review pause — a named reviewer must decide" : "No open review issues"}</h3>
    {open.map((issue) => <form key={issue.issue_id} onSubmit={submit(issue)} className={styles.form}>
      {issue.summary && <strong>{issue.kind ? `${issue.kind.replace("_", " ")}: ` : ""}{issue.summary}</strong>}
      <span className={styles.muted}>Issue <code>{issue.issue_id}</code> · revision {issue.revision_id ?? snapshot.revision.revision_id} · guarded by bundle hash <code>{snapshot.revision.input_bundle_hash.slice(0, 12)}…</code></span>
      <label>Decision <select name="decision_kind" defaultValue="accept_evidence">{DECISIONS.map((d) => <option key={d}>{d}</option>)}</select></label>
      <label>Rationale (recorded verbatim) <textarea name="rationale" required placeholder="Why this evidence is (or is not) sufficient" /></label>
      {snapshot.documents.length > 0 && <fieldset className={styles.checks}><legend>Evidence refs</legend>{snapshot.documents.map((doc) => { const id = docId(doc); return <label key={id}><input type="checkbox" name="evidence_refs" value={id} /> {id}</label>; })}</fieldset>}
      <button disabled={busy}>{busy ? "Recording…" : "Record decision"}</button>
    </form>)}
    <p role="alert" aria-live="polite" className={styles.error}>{error}{error.startsWith("403") ? " — a treasury_reviewer, officer or admin identity is required." : ""}</p>
    {closed.length > 0 && <div aria-live="polite">{closed.map((issue) => <div key={issue.issue_id} className={styles.row}><span className={`${styles.chip} ${styles.chipGood}`}>{issue.status}</span><code>{issue.issue_id}</code><span>{issue.decision_kind}{issue.rationale ? ` — ${issue.rationale}` : ""}{issue.resolved_by ? ` · by ${issue.resolved_by}` : ""}</span></div>)}</div>}
  </article>;
}
