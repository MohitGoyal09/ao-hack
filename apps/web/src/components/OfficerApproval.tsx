"use client";

import { FormEvent } from "react";
import { Approval, fix, OFFICER_ROLES, post, RunResult, Snapshot, useAction } from "@/lib/api";
import styles from "@/app/page.module.css";

type Props = { caseId: string; snapshot: Snapshot; result: RunResult | null; role: string; approval: Approval | null; onApproved: (approval: Approval) => void; onChange: () => Promise<void> };

export function OfficerApproval({ caseId, snapshot, result, role, approval, onApproved, onChange }: Props) {
  const { run, busy, error } = useAction(onChange);
  const { revision } = snapshot;
  // Worker calculation for the head revision: the API compares these exact strings against its stored numbers (409 on drift).
  const calc = snapshot.artifacts?.calculation;
  const approved = calc ? { approved_ratio: calc.ratio, approved_threshold: calc.threshold, approved_comparator: calc.comparator, approved_inputs: calc.inputs } : {};
  // Without an artifact the run result is only a preview when it was computed against the head revision's threshold.
  const preview = result && fix(result.calculation.threshold) === fix(revision.threshold) ? result : null;
  const blocked = snapshot.open_review_issues > 0;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    run(async () => {
      const binding = await post<Approval>(`/cases/${caseId}/officer-approval`, { revision_id: revision.revision_id, package_hash: snapshot.package_hash, decision: form.get("decision"), reason: form.get("reason"), ...approved });
      onApproved(binding);
      await onChange();
    });
  };

  return <article className={styles.panel}>
    <p className={styles.cardKicker}>6 · OFFICER APPROVAL · {snapshot.package_state}</p>
    <h3>Approve the exact draft — not an e-signature</h3>
    <dl className={styles.kv}>
      <dt>revision</dt><dd>{revision.revision_id}</dd>
      <dt>threshold</dt><dd>{revision.threshold} ({revision.rule_id})</dd>
      <dt>ratio</dt><dd>{calc ? `${calc.ratio} ${calc.comparator} ${calc.threshold} (worker calculation, sent verbatim)` : preview ? `${fix(preview.calculation.ratio)} ${preview.calculation.comparator} ${fix(preview.calculation.threshold)}` : "recalculate against this revision to preview; the API locks the fresh value"}</dd>
      <dt>inputs</dt><dd>{calc ? Object.entries(calc.inputs).map(([k, v]) => `${k}=${v}`).join(", ") : preview ? preview.evidence.map((fact) => `${fact.label}=${fact.value}`).join(", ") : "—"}</dd>
      <dt>package hash</dt><dd><code>{snapshot.package_hash}</code></dd>
    </dl>
    {!OFFICER_ROLES.has(role) && <p className={styles.stale}>Your identity has role <b>{role}</b>; the API will refuse with 403 (officer or admin required).</p>}
    <form onSubmit={submit} className={styles.form}>
      <label>Decision <select name="decision" defaultValue="approved"><option>approved</option><option>rejected</option></select></label>
      <label>Reason <input name="reason" required placeholder="Reviewed evidence manifest and calculation trace" /></label>
      <button disabled={busy || blocked} aria-describedby="approval-why">{busy ? "Binding…" : "Approve this revision"}</button>
      <span id="approval-why" className={styles.muted}>{blocked ? `Blocked: ${snapshot.open_review_issues} open review issue(s) must be resolved first.` : "Binds officer, revision, ratio, threshold, comparator, inputs and package hash; a stale hash returns 409."}</span>
    </form>
    <p role="alert" aria-live="polite" className={styles.error}>{error}</p>
    {approval && <div className={styles.stale} aria-live="polite">
      <strong>{approval.locked_summary}</strong>
      <dl className={styles.kv}>
        <dt>actor</dt><dd>{approval.actor} ({approval.role}) · {approval.decision} · {approval.timestamp}</dd>
        <dt>ratio</dt><dd>{approval.approved_ratio} {approval.approved_comparator} {approval.approved_threshold}</dd>
        <dt>inputs</dt><dd>{Object.entries(approval.approved_inputs).map(([k, v]) => `${k}=${v}`).join(", ") || "—"}</dd>
        <dt>package hash</dt><dd><code>{approval.package_hash}</code></dd>
      </dl>
    </div>}
  </article>;
}
