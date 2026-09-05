"use client";

import { FormEvent, useState } from "react";
import { api, useAction, UploadResult } from "@/lib/api";
import styles from "@/app/page.module.css";

const DOCUMENT_ROLES = ["credit_agreement", "amendment", "financial_statement", "supporting_evidence", "certificate_form"];

export function UploadDocument({ caseId, onChange }: { caseId: string; onChange: () => Promise<void> }) {
  const { run, busy, error } = useAction(onChange);
  const [result, setResult] = useState<UploadResult | null>(null);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const body = new FormData(form);
    for (const [key, value] of Array.from(body.entries())) if (value === "") body.delete(key); // optional dates: omit, don't send ""
    run(async () => {
      setResult(await api<UploadResult>(`/cases/${caseId}/documents`, { method: "POST", body }));
      form.reset();
      await onChange();
    });
  };

  return <article className={styles.panel}>
    <p className={styles.cardKicker}>1 · UPLOAD DOCUMENT</p>
    <h3>Intake an agreement, amendment or financials</h3>
    <form onSubmit={submit} className={styles.form}>
      <label>File (pdf, json, csv, xlsx, txt; ≤ 50 MB) <input name="file" type="file" required accept=".pdf,.json,.csv,.xlsx,.txt" /></label>
      <label>Document role <select name="document_role" defaultValue="credit_agreement">{DOCUMENT_ROLES.map((role) => <option key={role}>{role}</option>)}</select></label>
      <label>Title <input name="title" required placeholder="e.g. Aon credit agreement (SEC exhibit)" /></label>
      <div className={styles.inline}>
        <label>Effective date <input name="effective_date" type="date" /></label>
        <label>Period start <input name="period_start" type="date" /></label>
        <label>Period end <input name="period_end" type="date" /></label>
      </div>
      <button disabled={busy}>{busy ? "Uploading…" : "Upload → version + revision + job"}</button>
    </form>
    <p role="alert" aria-live="polite" className={styles.error}>{error}</p>
    {result && <dl className={styles.kv} aria-live="polite">
      <dt>document</dt><dd>{result.document_id} · version {result.version_number}</dd>
      <dt>sha256</dt><dd><code>{result.sha256}</code></dd>
      <dt>extraction</dt><dd>{result.extraction_state}</dd>
      <dt>revision</dt><dd>{result.revision_id}</dd>
      <dt>job</dt><dd>{result.job_id}</dd>
    </dl>}
  </article>;
}
