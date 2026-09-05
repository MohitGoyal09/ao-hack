"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, ApiError, Approval, CalculationArtifact, CaseSummary, docId, Snapshot, useIdentity } from "@/lib/api";
import s from "./workpaper.module.css";

// Snapshot artifact shapes (agent-docs/build-b-pipeline-snapshot.md). Kept local: the shared Snapshot type is still loose here.
type Src = { kind: string; document_id?: string; sha256?: string; label?: string; path?: string; attempted?: string[] };
type Span = { kind: string; section?: string; page?: number | null; sha256?: string };
type Rule = { external_rule_id: string; covenant_type: string; support_state: string; comparator: string; threshold: string; measurement_period: string; structured_rule?: { tiers?: { step: string; threshold: string }[]; formula?: string }; source_spans?: Span[] };
type Fact = { fact_key: string; amount: string; currency: string; unit_scale: number; period_start: string; period_end: string; evidence_state: string; source_spans?: { locator: string; source?: Src }[] };
type Calc = CalculationArtifact & { formula?: string; ebitda?: string; funded_debt?: string; fact_source?: Src; document_id?: string; document_sha256?: string; content_hash?: string };
type Artifacts = {
  calculation?: Calc;
  coverage?: { status: string; assessed: string[]; excluded: string[]; content_hash: string };
  evidence_manifest?: { extraction_state: string; document_id?: string; document_sha256?: string; fact_count?: number; sources?: { rule?: Src; facts?: Src }; content_hash: string };
  audit_trace?: { job_id: string; revision_id: string; stages: string[]; calculation_hash: string; content_hash: string };
  draft_package?: { revision_id: string; status: string; calculation_hash: string; coverage_hash: string; manifest_hash: string; trace_hash: string; content_hash: string };
};
type DocMeta = { document_id: string; title?: string; document_role?: string; version_number?: number; sha256?: string; extraction_state?: string; media_type?: string };

const scale = (n: number) => n === 1_000_000 ? "millions" : n === 1_000 ? "thousands" : n === 1 ? "units" : `×${n}`;
const src = (x?: Src) => !x ? "—" : x.kind === "bundled_fixture" ? `${x.label ?? "bundled fixture"} (${x.path ?? "?"}, sha256 ${x.sha256 ?? "?"})` : x.kind === "none" || x.kind === "skipped" ? `${x.kind}${x.attempted ? ` (tried: ${x.attempted.join(", ")})` : ""}` : `${x.kind} ${x.document_id ?? ""} sha256 ${x.sha256 ?? "?"}`;
const span = (x: Span) => x.kind === "document_hash" ? `document sha256 ${x.sha256}` : `${x.kind.replace("_", " ")} §${x.section ?? "?"}${x.page != null ? `, p. ${x.page}` : ""}`;
const headroom = (c: Calc) => { const d = Number(c.threshold) - Number(c.ratio); return (c.comparator.startsWith(">") ? -d : d).toFixed(2); };
const cls = (state: string) => state === "approved_draft" || state === "completed" ? s.chipGood : state === "failed" || state === "cancelled" ? s.chipBad : state === "draft" || state === "queued" || state === "running" || state === "waiting_review" ? s.chipWarn : s.chipNeutral;

function Section({ title, meta, children }: { title: string; meta?: string; children: React.ReactNode }) {
  return <section className={s.section}><h2>{title}{meta && <small>{meta}</small>}</h2>{children}</section>;
}

export default function WorkpaperPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const identity = useIdentity();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [info, setInfo] = useState<CaseSummary | null>(null);
  const [docs, setDocs] = useState<(DocMeta | null)[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [generatedAt, setGeneratedAt] = useState("");

  useEffect(() => { // identity change → re-read with the new bearer (same rule as the workbench)
    let alive = true;
    setError(null);
    Promise.all([api<Snapshot>(`/cases/${id}/snapshot`), api<CaseSummary>(`/cases/${id}`).catch(() => null)])
      .then(async ([snap, summary]) => {
        const metas = await Promise.all(snap.documents.map((d) => api<DocMeta>(`/documents/${docId(d)}`).catch(() => null)));
        if (!alive) return;
        setSnapshot(snap); setInfo(summary); setDocs(metas); setGeneratedAt(new Date().toISOString());
      })
      .catch((err) => { if (alive) setError(err instanceof ApiError ? err : new ApiError(0, String(err))); });
    return () => { alive = false; };
  }, [id, identity.kind, identity.label, identity.role]);

  const nav = <nav className={`${s.nav} ${s.noPrint}`}>
    <Link href={`/cases/${id}`}>← Back to the case workbench</Link>
    <button type="button" className={s.print} onClick={() => window.print()} disabled={!snapshot}>Print / Save as PDF</button>
  </nav>;

  if (error) return <main className={s.page}>{nav}<div className={s.state} role="alert">
    <h1>Workpaper unavailable</h1>
    <p className={s.error}>{error.status ? `${error.status} — ${error.detail}` : error.detail}</p>
    <p className={s.muted}>{error.status === 401 ? "Sign in or choose an offline identity on the workbench, then reopen this page." : error.status === 403 ? "This identity's role or organization may not read this case." : error.status === 404 ? "The case is unknown or not visible to this identity's organization." : "The Covenant API did not answer."}</p>
  </div></main>;
  if (!snapshot) return <main className={s.page}>{nav}<div className={s.state} aria-busy="true"><h1>Loading workpaper…</h1><p className={s.muted}>Reading the case snapshot for {id} as {identity.label} ({identity.role}).</p></div></main>;

  const { revision } = snapshot;
  const art = (snapshot.artifacts ?? {}) as Artifacts;
  const rules = (snapshot.covenant_rules ?? []) as Rule[];
  const facts = (snapshot.financial_facts ?? []) as Fact[];
  const issues = snapshot.review_issues ?? [];
  const calc = art.calculation;
  const manifest = art.evidence_manifest;
  const factSources = [calc?.fact_source, manifest?.sources?.facts, ...facts.flatMap((f) => (f.source_spans ?? []).map((sp) => sp.source))].filter((x): x is Src => !!x);
  const fixture = factSources.find((x) => x.kind === "bundled_fixture");
  const current: Approval | undefined = snapshot.approvals.find((a) => !a.superseded && a.decision === "approved");
  const borrower = info?.name.includes(":") ? info.name.split(":")[0].trim() : (info?.name ?? id);
  const hypothetical = info?.scenario_type === "comparison";

  return <main className={s.page}>
    {nav}
    <article className={s.sheet}>
      <div className={s.watermark} aria-hidden="true">Draft — not a signed certificate</div>
      <p className={s.banner} role="note">Draft — not a signed certificate</p>

      <header className={s.head}>
        <div>
          <p className={s.eyebrow}>Covenant compliance workpaper · case {snapshot.case_id}</p>
          <h1>{info?.name ?? snapshot.case_id}</h1>
          <p className={s.muted}>{info ? `${info.agreement} · ${info.agreement_version} · test date ${info.test_date}${info.covenant_name ? ` · ${info.covenant_name}` : ""}` : "Case narrative unavailable to this identity."}</p>
          {hypothetical && <span className={`${s.chip} ${s.chipWarn}`}>Labelled hypothetical — synthetic agreement</span>}
        </div>
        <div className={s.states}>
          <span className={`${s.chip} ${cls(snapshot.package_state)}`}>package {snapshot.package_state}</span>
          <span className={`${s.chip} ${cls(snapshot.run_state)}`}>run {snapshot.run_state}</span>
          <span className={`${s.chip} ${snapshot.open_review_issues ? s.chipWarn : s.chipGood}`}>{snapshot.open_review_issues} open review issue(s)</span>
        </div>
      </header>

      <Section title="1. Identification">
        <dl className={s.kv}>
          <dt>Case</dt><dd>{info?.name ?? snapshot.case_id} <span className={s.mono}>({snapshot.case_id})</span></dd>
          <dt>Borrower</dt><dd>{borrower}</dd>
          <dt>Facility / agreement</dt><dd>{info?.agreement ?? "—"}</dd>
          <dt>Controlling version</dt><dd>{info?.agreement_version ?? "—"}</dd>
          <dt>Test date</dt><dd>{revision.test_date}</dd>
          <dt>Revision</dt><dd>{revision.revision_id} ({revision.status}) · parent {revision.parent_revision ?? "none (initial revision)"}{revision.change_kind ? ` · ${revision.change_kind}` : ""}</dd>
          <dt>Rule / threshold</dt><dd>{revision.rule_id} · threshold {revision.threshold}</dd>
          <dt>Organization</dt><dd>{snapshot.organization_id ?? "offline demo org"}</dd>
          <dt>input_bundle_hash</dt><dd className={s.mono}>{revision.input_bundle_hash}</dd>
          <dt>rulebook_hash</dt><dd className={s.mono}>{revision.rulebook_hash}</dd>
          <dt>mapping_hash</dt><dd className={s.mono}>{revision.mapping_hash}</dd>
          <dt>calculation_hash</dt><dd className={s.mono}>{revision.calculation_hash}</dd>
          <dt>coverage_hash</dt><dd className={s.mono}>{revision.coverage_hash}</dd>
          <dt>package_hash</dt><dd className={s.mono}>{snapshot.package_hash}</dd>
        </dl>
      </Section>

      <Section title="2. Covenant rule" meta={`${rules.length} extracted for this revision`}>
        {rules.length === 0 && <p className={s.muted}>No extracted rule for revision {revision.revision_id} — the worker has not produced artifacts for this revision (upload a credit agreement to trigger it). The head revision tests {revision.rule_id} at {revision.threshold}.</p>}
        {rules.map((r) => <dl className={s.kv} key={r.external_rule_id}>
          <dt>Rule id</dt><dd>{r.external_rule_id} <span className={`${s.chip} ${r.support_state === "supported" ? s.chipGood : s.chipWarn}`}>{r.support_state}</span></dd>
          <dt>Covenant type</dt><dd>{r.covenant_type}</dd>
          <dt>Test</dt><dd className={s.mono}>ratio {r.comparator} {r.threshold}</dd>
          <dt>Measurement period</dt><dd>{r.measurement_period}</dd>
          <dt>Formula</dt><dd>{r.structured_rule?.formula ?? "—"}</dd>
          {r.structured_rule?.tiers && r.structured_rule.tiers.length > 0 && <><dt>Tiers</dt><dd>{r.structured_rule.tiers.map((t) => `${t.step}: ${t.threshold}`).join(" · ")}</dd></>}
          <dt>Source spans</dt><dd><ul className={s.list}>{(r.source_spans ?? []).map((sp, i) => <li key={i} className={sp.kind === "document_hash" ? s.mono : undefined}>{span(sp)}</li>)}</ul></dd>
        </dl>)}
      </Section>

      <Section title="3. Financial facts" meta={facts.length ? `${facts.length} facts · exact decimals` : undefined}>
        {facts.length === 0 ? <p className={s.muted}>No extracted financial facts for this revision.</p> : <div className={s.tableWrap}><table className={s.table}>
          <thead><tr><th>Fact</th><th>Amount</th><th>Currency / scale</th><th>Period</th><th>Evidence</th><th>Source span</th></tr></thead>
          <tbody>{facts.map((f) => <tr key={f.fact_key}>
            <td>{f.fact_key}</td><td className={s.num}>{f.amount}</td><td>{f.currency} {scale(f.unit_scale)}</td><td>{f.period_start} → {f.period_end}</td>
            <td><span className={`${s.chip} ${f.evidence_state === "accepted" ? s.chipGood : s.chipWarn}`}>{f.evidence_state}</span></td>
            <td>{(f.source_spans ?? []).map((sp, i) => <div key={i}>{sp.locator}<br /><span className={s.mono}>{src(sp.source)}</span></div>)}</td>
          </tr>)}</tbody>
        </table></div>}
      </Section>

      <Section title="4. Calculation" meta={calc?.content_hash ? `artifact ${calc.content_hash}` : undefined}>
        {!calc ? <p className={s.muted}>No worker calculation for revision {revision.revision_id}. This workpaper only prints numbers persisted as a calculation artifact; run the pipeline for this revision to populate this section.</p> : <>
          <p className={s.formula}>{calc.formula ?? `numerator ÷ denominator`} = {calc.ratio} ; test: {calc.ratio} {calc.comparator} {calc.threshold}</p>
          <div className={s.calc}>
            {calc.funded_debt && <div><small>Numerator · funded debt</small><strong>{calc.funded_debt}</strong></div>}
            {calc.ebitda && <div><small>Denominator · adjusted EBITDA</small><strong>{calc.ebitda}</strong></div>}
            <div><small>Ratio</small><strong>{calc.ratio}x</strong></div>
            <div><small>Threshold</small><strong>{calc.comparator} {calc.threshold}x</strong></div>
            <div><small>Headroom (threshold − ratio)</small><strong>{headroom(calc)}x</strong></div>
          </div>
          <div className={s.tableWrap}><table className={s.table}>
            <thead><tr><th>Input line</th><th>Amount (exact)</th></tr></thead>
            <tbody>{Object.entries(calc.inputs).map(([k, v]) => <tr key={k}><td>{k}</td><td className={s.num}>{v}</td></tr>)}</tbody>
          </table></div>
          <p className={s.muted}>Fact source: {src(calc.fact_source)}. Rule document: {calc.document_id ?? "—"} <span className={s.mono}>{calc.document_sha256 ?? ""}</span></p>
          {calc.period_check && (calc.period_check.matches
            ? <p className={s.muted}>Period check: facts period end {calc.period_check.facts_period_end} matches measurement period end {calc.period_check.measurement_period_end}.</p>
            : <p className={s.note}><b>Period mismatch.</b> Facts period end {calc.period_check.facts_period_end} ≠ measurement period end {calc.period_check.measurement_period_end}. {calc.period_check.note ?? "Arithmetic on extracted proxies; not a compliance verdict."} The ratio above is arithmetic only and carries no pass/fail meaning.</p>)}
        </>}
      </Section>

      <Section title="5. Coverage" meta={art.coverage?.content_hash ? `artifact ${art.coverage.content_hash}` : `${snapshot.coverage.state}`}>
        <p className={s.muted}>Declared scope: {art.coverage?.status ?? snapshot.coverage.state}. Assessed: {art.coverage?.assessed.join(", ") || snapshot.per_covenant_results.map((r) => r.rule_id).join(", ") || "none"}. Excluded: {art.coverage?.excluded.length ? art.coverage.excluded.join(", ") : "none listed"}.</p>
        <div className={s.tableWrap}><table className={s.table}>
          <thead><tr><th>Covenant</th><th>Support</th><th>Threshold</th><th>Result state</th></tr></thead>
          <tbody>
            {snapshot.per_covenant_results.map((r) => { const rule = rules.find((x) => x.external_rule_id === r.rule_id); return <tr key={r.rule_id}><td>{r.rule_id}</td><td>{rule?.support_state ?? (manifest?.extraction_state ?? "not extracted")}</td><td className={s.num}>{r.threshold}</td><td>{r.status}</td></tr>; })}
            {(art.coverage?.excluded ?? []).map((x) => <tr key={x}><td>{x}</td><td>unsupported / excluded</td><td className={s.num}>—</td><td>not assessed</td></tr>)}
          </tbody>
        </table></div>
        {manifest && <p className={s.muted}>Evidence manifest: extraction {manifest.extraction_state}{manifest.fact_count != null ? `, ${manifest.fact_count} facts` : ""}; rule source {src(manifest.sources?.rule)}; facts source {src(manifest.sources?.facts)}.</p>}
      </Section>

      <Section title="6. Review issues" meta={`${issues.length} on this revision`}>
        {issues.length === 0 ? <p className={s.muted}>{snapshot.open_review_issues ? `${snapshot.open_review_issues} open issue(s) reported without detail.` : "No review issues recorded for this revision."}</p> : <div className={s.tableWrap}><table className={s.table}>
          <thead><tr><th>Issue</th><th>Kind</th><th>Status</th><th>Decision</th><th>Rationale</th><th>Resolved by</th></tr></thead>
          <tbody>{issues.map((i) => <tr key={i.issue_id}><td className={s.mono}>{i.issue_id}</td><td>{i.kind ?? "—"}<br /><span className={s.muted}>{i.summary}</span></td><td><span className={`${s.chip} ${i.status === "resolved" ? s.chipGood : i.status === "open" ? s.chipWarn : s.chipNeutral}`}>{i.status}</span></td><td>{i.decision_kind ?? "—"}</td><td>{i.rationale ?? "—"}</td><td>{i.resolved_by ?? "—"}</td></tr>)}</tbody>
        </table></div>}
      </Section>

      <Section title="7. Officer approvals" meta={`${snapshot.approvals.length} recorded`}>
        {snapshot.approvals.length === 0 && <p className={s.muted}>No officer approval recorded. This draft is unapproved.</p>}
        {snapshot.approvals.map((a, i) => <div className={s.approval} key={`${a.target_revision}-${a.timestamp}-${i}`}>
          <div className={s.approvalHead}>
            <span><b>{a.decision}</b> · revision {a.target_revision} · {a.actor} ({a.role}) · {a.timestamp}</span>
            {a.superseded ? <span className={s.stamp}>Superseded</span> : <span className={`${s.chip} ${a.decision === "approved" ? s.chipGood : s.chipBad}`}>{a.decision === "approved" ? "current approval" : a.decision}</span>}
          </div>
          <span className={s.mono}>package_hash {a.package_hash}</span>
          {a.reason && <span>Reason: {a.reason}</span>}
          {a.locked_summary ? <span>{a.locked_summary}</span> : a.approved_ratio && <span>Locked: ratio {a.approved_ratio} {a.approved_comparator} {a.approved_threshold}; inputs {Object.entries(a.approved_inputs ?? {}).map(([k, v]) => `${k}=${v}`).join(", ") || "—"}</span>}
        </div>)}
        <p className={s.muted}>{current ? `Current approval binds revision ${current.target_revision} and package_hash ${current.package_hash === snapshot.package_hash ? "(matches this head)" : "(does NOT match this head — a newer revision exists)"}.` : "No current approval binds this head revision."} An internal approval is not an electronic signature or delivery to a lender.</p>
      </Section>

      <Section title="8. Documents" meta={`${snapshot.documents.length} · append-only`}>
        <div className={s.tableWrap}><table className={s.table}>
          <thead><tr><th>Document</th><th>Title / role</th><th>Version</th><th>sha256</th><th>Extraction</th></tr></thead>
          <tbody>{snapshot.documents.map((d, i) => { const m = docs[i]; return <tr key={docId(d)}><td className={s.mono}>{docId(d)}</td><td>{m ? `${m.title ?? "—"} · ${m.document_role ?? "—"}` : "catalog seed document (no uploaded version)"}</td><td className={s.num}>{m?.version_number ?? "—"}</td><td className={s.mono}>{m?.sha256 ?? "—"}</td><td>{m?.extraction_state ?? "—"}</td></tr>; })}</tbody>
        </table></div>
      </Section>

      <Section title="9. Assumptions, exclusions and required statements">
        <ul className={s.list}>
          <li><b>Draft only.</b> This workpaper is prepared for officer review. It is not a signed compliance certificate, not an electronic signature, and not delivery to any lender or agent.</li>
          <li><b>Declared scope only.</b> A supported leverage result covers the assessed covenant(s) listed in section 5. It is not a statement of full agreement compliance; other obligations are not evaluated here.</li>
          <li><b>Not legal advice.</b> A calculated failed test is a result requiring review, not a determination of default, event of default or lender remedies.</li>
          {fixture && <li><b>Bundled-fixture facts.</b> Financial facts were read from {fixture.label ?? "a bundled fixture"} ({fixture.path}, sha256 <span className={s.mono}>{fixture.sha256}</span>), not from a financial statement uploaded to this case. Replace with the borrower&apos;s own statements before relying on the numbers.</li>}
          {calc?.period_check && !calc.period_check.matches && <li><b>Financial period mismatch.</b> The facts cover a period ending {calc.period_check.facts_period_end} while the covenant measures the period ending {calc.period_check.measurement_period_end}. The ratio in section 4 is arithmetic on extracted proxies and is not a compliance result for the test date.</li>}
          {!calc && <li><b>No calculation.</b> No calculation artifact exists for revision {revision.revision_id}; sections 4 and 5 report scope only.</li>}
          {manifest?.extraction_state === "unsupported" && <li><b>Unsupported extraction.</b> The pipeline could not extract a supported covenant rule from the uploaded document; the covenant is listed as unsupported and no result is produced.</li>}
          {hypothetical && <li><b>Labelled hypothetical.</b> This case uses synthetic agreement terms for comparison; nothing here describes any issuer&apos;s actual compliance.</li>}
          {snapshot.open_review_issues > 0 && <li><b>Open review.</b> {snapshot.open_review_issues} review issue(s) remain open; the package is not ready for officer approval.</li>}
          {!current && <li><b>Unapproved.</b> No current officer approval binds revision {revision.revision_id}.</li>}
          <li><b>Exact values.</b> Amounts and ratios are printed verbatim from the persisted artifacts (no rounding beyond the stored two decimals); headroom is display arithmetic on those values.</li>
        </ul>
      </Section>

      <Section title="10. Audit trace" meta={`event #${snapshot.last_event_sequence}`}>
        <dl className={s.kv}>
          <dt>Persisted events</dt><dd>{snapshot.last_event_sequence} append-only case events (last sequence {snapshot.last_event_sequence}).</dd>
          {art.audit_trace && <>
            <dt>Worker trace</dt><dd>job {art.audit_trace.job_id} · revision {art.audit_trace.revision_id} · stages {art.audit_trace.stages.join(" → ")}</dd>
            <dt>Trace head hash</dt><dd className={s.mono}>{art.audit_trace.content_hash}</dd>
            <dt>Chained calculation</dt><dd className={s.mono}>{art.audit_trace.calculation_hash}</dd>
          </>}
          {art.draft_package && <>
            <dt>Draft package hash</dt><dd className={s.mono}>{art.draft_package.content_hash} (status {art.draft_package.status})</dd>
            <dt>Package links</dt><dd className={s.mono}>calculation {art.draft_package.calculation_hash}<br />coverage {art.draft_package.coverage_hash}<br />manifest {art.draft_package.manifest_hash}<br />trace {art.draft_package.trace_hash}</dd>
          </>}
          {!art.audit_trace && !art.draft_package && <><dt>Worker trace</dt><dd className={s.muted}>No audit trace artifact for this revision.</dd></>}
        </dl>
      </Section>

      <footer className={s.footer}>
        <span>Generated {generatedAt} · viewed as {identity.label} ({identity.role}) · revision {revision.revision_id}</span>
        <span>Prepared for officer review. This draft is not an electronic signature.</span>
      </footer>
    </article>
  </main>;
}
