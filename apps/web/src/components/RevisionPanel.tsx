"use client";

import { FormEvent, useState } from "react";
import { api, docId, ImpactResult, post, Revision, RevisionResult, short, Snapshot, useAction } from "@/lib/api";
import styles from "@/app/page.module.css";

const list = (values?: string[]) => values?.length ? values.join(", ") : "none";

export function RevisionPanel({ caseId, snapshot, revisions, onChange }: { caseId: string; snapshot: Snapshot; revisions: Revision[]; onChange: () => Promise<void> }) {
  const { run, busy, error } = useAction(onChange);
  const [created, setCreated] = useState<RevisionResult | null>(null);
  const [impact, setImpact] = useState<ImpactResult | null>(null);
  const head = snapshot.revision.revision_id;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const threshold = String(form.get("new_threshold") ?? "").trim();
    run(async () => {
      const result = await post<RevisionResult>(`/cases/${caseId}/revisions`, {
        expected_parent_revision: head,
        change_kind: form.get("change_kind"),
        documents: form.getAll("documents"),
        facts: [],
        new_threshold: threshold || null,
      });
      setCreated(result);
      setImpact(await api<ImpactResult>(`/cases/${caseId}/revisions/${result.revision_id}/impact`));
      await onChange();
    });
  };

  return <article className={styles.panel}>
    <p className={styles.cardKicker}>5 · REVISIONS · head {head}</p>
    <h3>Amendments create revisions, never overwrite</h3>
    <div className={styles.tableWrap}><table className={styles.table}>
      <thead><tr><th>Revision</th><th>Parent</th><th>Kind</th><th>Threshold</th><th>Status</th><th>Bundle hash</th></tr></thead>
      <tbody>{revisions.map((rev) => <tr key={rev.revision_id}><td>{rev.revision_id}{rev.revision_id === head ? " (head)" : ""}</td><td>{rev.parent_revision ?? "—"}</td><td>{rev.change_kind ?? "—"}</td><td>{rev.threshold}</td><td>{rev.revision_id === head ? "current" : "superseded"}</td><td><code>{short(rev.input_bundle_hash)}</code></td></tr>)}</tbody>
    </table></div>
    <form onSubmit={submit} className={styles.form}>
      <p className={styles.cardKicker}>RECORD AMENDMENT (parent must still be {head})</p>
      <div className={styles.inline}>
        <label>Change kind <select name="change_kind" defaultValue="amendment"><option>amendment</option><option>correction</option><option>controlled_update</option></select></label>
        <label>New threshold (e.g. 4.00; blank keeps {snapshot.revision.threshold}) <input name="new_threshold" inputMode="decimal" pattern="^\d+(\.\d+)?$" placeholder="4.00" /></label>
      </div>
      {snapshot.documents.length > 0 && <fieldset className={styles.checks}><legend>Documents replaced/added by this change</legend>{snapshot.documents.map((doc) => { const id = docId(doc); return <label key={id}><input type="checkbox" name="documents" value={id} /> {id}</label>; })}</fieldset>}
      <button disabled={busy}>{busy ? "Recording…" : "Record amendment → new revision"}</button>
    </form>
    <p role="alert" aria-live="polite" className={styles.error}>{error}</p>
    {created && <div className={styles.stale} aria-live="polite">
      <strong>Revision {created.revision_id} created from {created.revision.parent_revision}.</strong> Threshold {created.revision.threshold}.<br />
      Invalidated approvals: {list(created.impact_pending.invalidated_decision_ids)} · stale artifacts: {list(created.impact_pending.stale_artifact_ids)} · review required: {list(created.impact_pending.review_requirements)}
    </div>}
    {impact && <dl className={styles.kv}>
      <dt>changed inputs</dt><dd>{list(impact.changed_inputs)}</dd>
      <dt>affected rules</dt><dd>{list(impact.affected_rule_ids)}</dd>
      <dt>stale artifacts</dt><dd>{list(impact.stale_artifact_ids)}</dd>
      <dt>review requirements</dt><dd>{list(impact.review_requirements)}</dd>
      <dt>invalidated decisions</dt><dd>{list(impact.impact.invalidated_decision_ids)}</dd>
    </dl>}
    <p className={styles.cardKicker}>APPROVALS BOUND TO REVISIONS</p>
    {snapshot.approvals.length === 0 ? <p className={styles.muted}>None yet.</p> : snapshot.approvals.map((approval, index) => <div key={index} className={styles.row}>
      <span className={`${styles.chip} ${approval.superseded ? styles.chipBad : approval.decision === "approved" ? styles.chipGood : styles.chipWarn}`}>{approval.superseded ? "superseded" : approval.decision}</span>
      <span>{approval.target_revision} · {approval.actor} ({approval.role}) · ratio {approval.approved_ratio ?? "n/a"} {approval.approved_comparator ?? ""} {approval.approved_threshold ?? ""}</span>
      <code>{short(approval.package_hash)}</code>
    </div>)}
  </article>;
}
