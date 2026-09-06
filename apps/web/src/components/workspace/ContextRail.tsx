"use client";

import { docId, short, Snapshot } from "@/lib/api";
import { deriveStages } from "@/lib/workflow";
import { StatusBadge } from "./StatusBadge";
import { useWorkspacePreference } from "./useWorkspacePreference";
import type { DomainEvent } from "@/components/EventFeed";
import s from "./workspace.module.css";

type Props = {
  snapshot: Snapshot | null;
  events: DomainEvent[];
  disconnected: boolean;
  collapsed: boolean;
  onToggleCollapse: () => void;
  selectedSource: string | null;
  onSelectSource: (source: string | null) => void;
  onSelectStage: (anchorId: string) => void;
};

type Panel = "progress" | "outputs" | "context";
type OpenPanels = Record<Panel, boolean>;

const STAGE_ANCHOR: Record<string, string> = {
  documents: "card-documents",
  agreement: "card-definitions",
  definitions: "card-definitions",
  evidence: "card-evidence",
  calculation: "card-calculation",
  review: "card-review",
  package: "card-package",
};

export function ContextRail({ snapshot, events, disconnected, collapsed, onToggleCollapse, selectedSource, onSelectSource, onSelectStage }: Props) {
  const [openPanels, setOpenPanels] = useWorkspacePreference<OpenPanels>("covenant.workspace.context-rail-panels", { progress: true, outputs: false, context: false });
  const stages = deriveStages(snapshot, events);
  const current = stages.find((stage) => stage.state === "blocked") ?? stages.find((stage) => stage.state === "failed") ?? stages.find((stage) => stage.state === "running") ?? stages.find((stage) => stage.state !== "complete") ?? stages.at(-1);
  const rules = (snapshot?.covenant_rules ?? []) as { external_rule_id: string; support_state: string }[];
  const facts = (snapshot?.financial_facts ?? []) as { fact_key: string; evidence_state: string }[];
  const calc = snapshot?.artifacts?.calculation;
  const togglePanel = (panel: Panel) => setOpenPanels((currentPanels) => ({ ...currentPanels, [panel]: !currentPanels[panel] }));

  if (collapsed) {
    return (
      <aside className={`${s.contextRail} ${s.railCollapsed}`} aria-label="Case context, collapsed">
        <button type="button" className={s.iconButton} onClick={onToggleCollapse} aria-label="Open case context">⟨</button>
      </aside>
    );
  }

  const panelId = (panel: Panel) => `case-context-${panel}`;
  return (
    <aside className={s.contextRail} aria-label="Case context">
      <div className={s.railHead}>
        <strong>Context</strong>
        <button type="button" className={s.iconButton} onClick={onToggleCollapse} aria-label="Close case context">⟩</button>
      </div>

      <section aria-label="Progress">
        <button type="button" className={s.stageItem} aria-expanded={openPanels.progress} aria-controls={panelId("progress")} onClick={() => togglePanel("progress")}>
          <span className={s.stageRow}><strong>Progress</strong>{current ? <StatusBadge state={current.state} /> : <StatusBadge state="pending" />}</span>
          <small>{current ? current.title : "Open a case to begin"}</small>
        </button>
        {openPanels.progress && <div id={panelId("progress")}>
          {current && <p className={s.finePrintLight}>{current.detail}{current.state !== "complete" ? ` Next: ${current.action}` : ""}</p>}
          <ol className={s.stageList} aria-label="Seven workflow stages">
            {stages.map((stage, index) => (
              <li key={stage.id}>
                <button type="button" className={s.stageItem} onClick={() => onSelectStage(STAGE_ANCHOR[stage.id] ?? "card-case")} aria-label={`Stage ${index + 1}: ${stage.title}, ${stage.state}. ${stage.detail}`}>
                  <span className={s.stageRow}><span>{index + 1}. {stage.title}</span><StatusBadge state={stage.state} /></span>
                </button>
              </li>
            ))}
          </ol>
          <p className={s.finePrintLight}>{snapshot ? `Run ${snapshot.run_state} · ${snapshot.revision.revision_id}` : "No run loaded."}<br />{disconnected ? "Disconnected — retry in the conversation." : "Connected"}</p>
        </div>}
      </section>

      <section aria-label="Outputs">
        <button type="button" className={s.stageItem} aria-expanded={openPanels.outputs} aria-controls={panelId("outputs")} onClick={() => togglePanel("outputs")}>
          <span className={s.stageRow}><strong>Outputs</strong></span>
          <small>{calc ? "Calculation and draft package" : "No generated output yet"}</small>
        </button>
        {openPanels.outputs && <div id={panelId("outputs")}>
          {!snapshot ? <p className={s.finePrintLight}>Open a case to inspect outputs.</p> : <>
            <div className={s.evItem}>Calculation: {calc ? <code>{calc.ratio} {calc.comparator} {calc.threshold}</code> : "not available"}</div>
            <div className={s.evItem}>Evidence package: {snapshot.documents.length} documents · {facts.length} facts · {rules.length} definitions</div>
            <div className={s.evItem}>Draft certificate: <StatusBadge state={snapshot.package_state} /> <code>{short(snapshot.package_hash)}</code></div>
            <div className={s.evItem}>Review record: {snapshot.open_review_issues} open issue(s)</div>
          </>}
        </div>}
      </section>

      <section aria-label="Context">
        <button type="button" className={s.stageItem} aria-expanded={openPanels.context} aria-controls={panelId("context")} onClick={() => togglePanel("context")}>
          <span className={s.stageRow}><strong>Context</strong></span>
          <small>{snapshot ? `${snapshot.documents.length} documents · ${rules.length} citations` : "Documents and citations"}</small>
        </button>
        {openPanels.context && <div id={panelId("context")}>
          {!snapshot ? <p className={s.finePrintLight}>Open a case to inspect sources.</p> : <>
            <h4>Documents</h4>
            {snapshot.documents.length ? snapshot.documents.map((document) => <div key={docId(document)} className={s.evItem}><code>{docId(document)}</code></div>) : <p className={s.finePrintLight}>No documents yet.</p>}
            <h4>Citations</h4>
            {rules.length ? rules.map((rule) => <div key={rule.external_rule_id} className={s.evItem}><code>{rule.external_rule_id}</code> <StatusBadge state={rule.support_state} /></div>) : <p className={s.finePrintLight}>No cited definitions yet.</p>}
            <h4>Current revision</h4>
            <div className={s.evItem}><code>{snapshot.revision.revision_id}</code><br />threshold {snapshot.revision.threshold} · <code>{short(snapshot.revision.input_bundle_hash)}</code></div>
            {selectedSource ? <div className={`${s.evItem} ${s.evSelected}`}><code>{selectedSource}</code><br /><button type="button" className={s.citeButton} onClick={() => onSelectSource(null)}>Clear source</button></div> : <p className={s.finePrintLight}>Select a citation in the conversation to inspect it here.</p>}
          </>}
        </div>}
      </section>
    </aside>
  );
}
