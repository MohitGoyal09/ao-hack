"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, CaseListItem, CaseSummary, createCase, listCases, useIdentity } from "@/lib/api";
import { CaseRail } from "@/components/workspace/CaseRail";
import { CopilotComposer } from "@/components/workspace/CopilotComposer";
import { ChatTranscript } from "@/components/workspace/Conversation";
import { ContextRail } from "@/components/workspace/ContextRail";
import { WorkspaceShell, scrollToCard } from "@/components/workspace/WorkspaceShell";
import { useWorkspacePreference } from "@/components/workspace/useWorkspacePreference";
import s from "@/components/workspace/workspace.module.css";

export default function HomePage() {
  const router = useRouter();
  const identity = useIdentity();
  const [templates, setTemplates] = useState<CaseSummary[]>([]);
  const [templatesError, setTemplatesError] = useState("");
  const [mine, setMine] = useState<CaseListItem[] | null>(null);
  const [railCollapsed, setRailCollapsed] = useWorkspacePreference("covenant.workspace.case-rail-collapsed", false);
  const [contextCollapsed, setContextCollapsed] = useWorkspacePreference("covenant.workspace.context-rail-collapsed", false);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [creatingId, setCreatingId] = useState<string | null>(null);

  useEffect(() => {
    api<CaseSummary[]>("/demo-cases").then(setTemplates).catch((err: Error) => setTemplatesError(`${err.message} — start the API service to load the cases.`));
  }, []);
  useEffect(() => { listCases().then(setMine).catch(() => setMine(null)); }, [identity.kind, identity.label]);

  const handleStartTemplate = async (templateId: string) => {
    setCreatingId(templateId);
    try {
      const created = await createCase({ template_case_id: templateId });
      router.push(`/cases/${created.case_id}`);
    } catch (err) {
      setTemplatesError(err instanceof Error ? err.message : String(err));
      setCreatingId(null);
    }
  };

  return (
    <WorkspaceShell
      rail={
        <CaseRail
          templates={templates}
          templatesError={templatesError}
          myCases={mine}
          activeId={null}
          openIssues={0}
          collapsed={railCollapsed}
          onToggleCollapse={() => setRailCollapsed((v) => !v)}
          onCreated={(id) => router.push(`/cases/${id}`)}
        />
      }
      main={
        <>
          <article className={s.workspaceIntro} aria-label="Start a covenant review">
            <p className={s.kicker}>Covenant Certificate · Office of the CFO</p>
            <h1>Start a covenant review</h1>
            <p>Choose a prepared starter below or attach a document. Attachments create a private working case, then begin a background intake job.</p>
            <div className={s.workspaceStart} aria-label="Workspace capabilities"><span>agreement precedence</span><span>evidence mapping</span><span>deterministic calculation</span><span>controller review</span></div>

            {templates.length > 0 && (
              <div style={{ marginTop: 24, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
                {templates.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    disabled={creatingId !== null}
                    onClick={() => handleStartTemplate(t.id)}
                    style={{
                      textAlign: "left",
                      padding: "16px 18px",
                      background: "#fafafa",
                      border: "1px solid #dedede",
                      borderRadius: "8px",
                      cursor: creatingId !== null ? "wait" : "pointer",
                      display: "flex",
                      flexDirection: "column",
                      gap: "6px",
                      transition: "border-color 150ms ease, box-shadow 150ms ease",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <strong style={{ fontSize: "14px", color: "#111" }}>{t.name}</strong>
                      <span style={{ fontSize: "11px", color: "#777", background: "#eaeaea", padding: "2px 6px", borderRadius: "4px" }}>{t.scenario_type}</span>
                    </div>
                    <span style={{ fontSize: "12px", color: "#555" }}>{t.agreement}</span>
                    <small style={{ fontSize: "11px", color: "#777", marginTop: 4 }}>{t.narrative}</small>
                    <span style={{ fontSize: "12px", color: "#0066cc", marginTop: 6, fontWeight: 600 }}>{creatingId === t.id ? "Creating case…" : "Open case →"}</span>
                  </button>
                ))}
              </div>
            )}
            {templatesError && <p style={{ color: "#d93838", marginTop: 12, fontSize: "13px" }}>{templatesError}</p>}
          </article>
          <ChatTranscript caseName={null} />
        </>
      }
      composer={<CopilotComposer role={identity.role} templates={templates} onCreated={(id) => router.push(`/cases/${id}`)} />}
      contextCollapsed={contextCollapsed}
      context={
        <ContextRail
          snapshot={null}
          events={[]}
          disconnected={false}
          collapsed={contextCollapsed}
          onToggleCollapse={() => setContextCollapsed((v) => !v)}
          selectedSource={selectedSource}
          onSelectSource={setSelectedSource}
          onSelectStage={scrollToCard}
          documentMeta={{}}
          onPreviewDocument={() => undefined}
        />
      }
    />
  );
}
