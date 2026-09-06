"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { CaseListItem, CaseSummary, createCase, useAction, useIdentity } from "@/lib/api";
import { canMutate, roleExplanation } from "@/lib/workflow";
import { StatusBadge } from "./StatusBadge";
import s from "./workspace.module.css";

type Props = {
  templates: CaseSummary[];
  templatesError: string;
  myCases: CaseListItem[] | null;
  activeId: string | null;
  openIssues: number;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onCreated: (caseId: string) => void;
};

export function CaseRail({ templates, templatesError, myCases, activeId, openIssues, collapsed, onToggleCollapse, onCreated }: Props) {
  const identity = useIdentity();
  const { run, busy, error } = useAction();
  const [query, setQuery] = useState("");
  const [newCaseOpen, setNewCaseOpen] = useState(false);
  const mutate = canMutate(identity.role);

  const q = query.trim().toLowerCase();
  const filteredTemplates = useMemo(
    () => (q ? templates.filter((t) => `${t.name} ${t.id} ${t.narrative}`.toLowerCase().includes(q)) : templates),
    [templates, q],
  );
  const filteredMine = useMemo(
    () => (myCases && q ? myCases.filter((c) => `${c.name} ${c.case_id}`.toLowerCase().includes(q)) : myCases),
    [myCases, q],
  );

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    run(async () => {
      const created = await createCase({
        template_case_id: String(form.get("template_case_id")),
        name: String(form.get("name") ?? "").trim() || undefined,
        test_date: String(form.get("test_date") ?? "") || undefined,
      });
      onCreated(created.case_id);
    });
  };

  if (collapsed) {
    return (
      <aside className={`${s.caseRail} ${s.railCollapsed}`} aria-label="Case rail, collapsed">
        <button type="button" className={s.iconButton} onClick={onToggleCollapse} aria-label="Expand case rail">☰</button>
      </aside>
    );
  }

  return (
    <aside className={s.caseRail} aria-label="Case rail">
      <div className={s.railHead}>
        <strong>Cases</strong>
        <button type="button" className={s.iconButton} onClick={onToggleCollapse} aria-label="Collapse case rail">⟨</button>
      </div>
      <label className={s.searchLabel}>Search cases
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter by name or id" aria-label="Search cases" />
      </label>

      <section aria-label="Start a case">
        <button type="button" className={s.newCaseToggle} aria-expanded={newCaseOpen} aria-controls="new-case-form" onClick={() => setNewCaseOpen((open) => !open)}><span>New case</span><b aria-hidden="true">{newCaseOpen ? "−" : "+"}</b></button>
        {newCaseOpen && <div className={s.newCaseBody} id="new-case-form">
          {!mutate ? <p className={s.gateNote}>{roleExplanation("treasury_reviewer, officer or admin")} Case creation is disabled.</p> : <form onSubmit={submit} className={s.stackForm}>
            <label>Prepared starter<select name="template_case_id" required>{filteredTemplates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
            <label>Case name <input name="name" maxLength={240} placeholder="Optional working name" /></label>
            <label>Test date <input name="test_date" type="date" /></label>
            <button disabled={busy || !filteredTemplates.length}>{busy ? "Creating…" : "Create private case"}</button>
          </form>}
          <p role="alert" aria-live="polite" className={s.inlineError}>{error || templatesError}</p>
          <p className={s.finePrint}>{filteredTemplates.length ? "Each starter creates a fresh private case. Templates never change." : "No starter matches this search."}</p>
        </div>}
      </section>

      <section aria-label="Your cases">
        <p className={s.kicker}>Your cases · {identity.label}</p>
        {!filteredMine ? <p className={s.finePrint}>Sign in or pick an offline identity to list cases.</p>
          : filteredMine.length === 0 ? <p className={s.finePrint}>No cases yet — create one above.</p>
          : <ul className={s.caseList}>
            {filteredMine.map((c) => (
              <li key={c.case_id}>
                <Link href={`/cases/${c.case_id}`} className={`${s.caseItem} ${c.case_id === activeId ? s.caseItemActive : ""}`} aria-current={c.case_id === activeId ? "true" : undefined}>
                  <strong>{c.name}</strong>
                  <small><code>{c.case_id}</code>{c.case_id === activeId && openIssues > 0 ? ` · ${openIssues} open review` : ""}</small>
                </Link>
              </li>
            ))}
          </ul>}
      </section>

      <div className={s.inboxRow}>
        <span>Review inbox</span>
        {openIssues > 0 ? <StatusBadge state="blocked" label={`${openIssues} open`} /> : <StatusBadge state="complete" label="clear" />}
      </div>
    </aside>
  );
}
