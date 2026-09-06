"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, CaseListItem, CaseSummary, listCases, useIdentity } from "@/lib/api";
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

  useEffect(() => {
    api<CaseSummary[]>("/demo-cases").then(setTemplates).catch((err: Error) => setTemplatesError(`${err.message} — start the API service to load the cases.`));
  }, []);
  useEffect(() => { listCases().then(setMine).catch(() => setMine(null)); }, [identity.kind, identity.label]);

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
            <p>Choose a prepared starter in Cases or attach a document below. Attachments always create a private working case, then begin a background intake job.</p>
            <div className={s.workspaceStart} aria-label="Workspace capabilities"><span>agreement precedence</span><span>evidence mapping</span><span>deterministic calculation</span><span>controller review</span></div>
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
        />
      }
    />
  );
}
