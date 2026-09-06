"use client";

import Link from "next/link";
import { Approval, CaseSummary, RunResult, Snapshot } from "@/lib/api";
import styles from "@/app/page.module.css";

export function DownloadPackage({ info, snapshot, result, approval }: { info: CaseSummary | null; snapshot: Snapshot; result: RunResult | null; approval: Approval | null }) {
  const current = snapshot.approvals.find((a) => !a.superseded && a.decision === "approved") ?? null;
  const calculation = result?.calculation ?? snapshot.artifacts?.calculation ?? null;
  const blocked = snapshot.open_review_issues > 0;
  const download = () => {
    const { revision } = snapshot;
    const pkg = {
      draft_mark: "DRAFT — not a signed certificate",
      generated_at: new Date().toISOString(),
      case: info, revision, run_state: snapshot.run_state, package_state: snapshot.package_state,
      hashes: { input_bundle_hash: revision.input_bundle_hash, rulebook_hash: revision.rulebook_hash, mapping_hash: revision.mapping_hash, calculation_hash: revision.calculation_hash, coverage_hash: revision.coverage_hash, package_hash: snapshot.package_hash },
      calculation, certificate: result?.certificate ?? null, citations: result?.citations ?? [], evidence: result?.evidence ?? [],
      approvals: snapshot.approvals, current_approval: current, locked_summary: approval?.locked_summary ?? null,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(pkg, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `covenant-package-${snapshot.case_id}-${revision.revision_id}.json`; anchor.click(); URL.revokeObjectURL(url);
  };
  return <article className={styles.panel}>
    <p className={styles.cardKicker}>7 · PACKAGE</p>
    <h3>Download the draft package</h3>
    <p className={styles.muted}>JSON containing head revision {snapshot.revision.revision_id}, hashes, the last calculation, every approval and the locked summary. Always marked <b>DRAFT — not a signed certificate</b>.</p>
    <span className={`${styles.chip} ${current ? styles.chipGood : styles.chipWarn}`}>{current ? `approved by ${current.actor}` : "unapproved draft"}</span>
    <button type="button" onClick={download} disabled={blocked} aria-describedby="download-why">Download draft package</button>
    <span id="download-why" className={styles.muted}>{blocked ? `Disabled: ${snapshot.open_review_issues} open review issue(s) — resolve them first.` : calculation ? "Includes the calculation stored for this revision." : "No calculation yet — package will carry revision, hashes and approvals only."}</span>
    <Link href={`/cases/${snapshot.case_id}/workpaper`} className={styles.muted}>Open printable workpaper (DRAFT — not a signed certificate) →</Link>
  </article>;
}
