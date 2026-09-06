"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, CaseListItem, CaseSummary, listCases, UploadResult, useIdentity } from "@/lib/api";
import { CaseRail } from "@/components/workspace/CaseRail";
import { CopilotComposer } from "@/components/workspace/CopilotComposer";
import { ContextRail } from "@/components/workspace/ContextRail";
import { Conversation } from "@/components/workspace/Conversation";
import { WorkspaceShell, scrollToCard } from "@/components/workspace/WorkspaceShell";
import { useCaseWorkspace } from "@/components/workspace/useCaseWorkspace";
import { useWorkspacePreference } from "@/components/workspace/useWorkspacePreference";
import s from "@/components/workspace/workspace.module.css";

export default function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const identity = useIdentity();
  const [info, setInfo] = useState<CaseSummary | null>(null);
  const [templates, setTemplates] = useState<CaseSummary[]>([]);
  const [templatesError, setTemplatesError] = useState("");
  const [mine, setMine] = useState<CaseListItem[] | null>(null);
  const [railCollapsed, setRailCollapsed] = useWorkspacePreference("covenant.workspace.case-rail-collapsed", false);
  const [contextCollapsed, setContextCollapsed] = useWorkspacePreference("covenant.workspace.context-rail-collapsed", false);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<UploadResult | null>(null);
  const ws = useCaseWorkspace(id);

  useEffect(() => {
    setUploaded(null);
    api<CaseSummary>(`/cases/${id}`).then(setInfo).catch(() => setInfo(null));
  }, [id]);
  useEffect(() => {
    api<CaseSummary[]>("/demo-cases").then(setTemplates).catch((err: Error) => setTemplatesError(err.message));
  }, []);
  useEffect(() => { listCases().then(setMine).catch(() => setMine(null)); }, [identity.kind, identity.label]);

  return (
    <WorkspaceShell
      rail={
        <CaseRail
          templates={templates}
          templatesError={templatesError}
          myCases={mine}
          activeId={id}
          openIssues={ws.snapshot?.open_review_issues ?? 0}
          collapsed={railCollapsed}
          onToggleCollapse={() => setRailCollapsed((v) => !v)}
          onCreated={(caseId) => router.push(`/cases/${caseId}`)}
        />
      }
      main={
        <Conversation
            caseId={id}
            caseName={info?.name ?? null}
            snapshot={ws.snapshot}
            jobs={ws.jobs}
            events={ws.events}
            revisions={ws.revisions}
            error={ws.error}
            disconnected={ws.disconnected}
            active={ws.active}
            role={identity.role}
            uploaded={uploaded}
            refresh={ws.refresh}
            onSelectSource={setSelectedSource}
          />
      }
      composer={<CopilotComposer caseId={id} caseName={info?.name} role={identity.role} templates={templates} onCreated={(caseId) => router.push(`/cases/${caseId}`)} onUploaded={async (result) => { setUploaded(result); await ws.refresh(); }} />}
      contextCollapsed={contextCollapsed}
      context={
        <ContextRail
          snapshot={ws.snapshot}
          events={ws.events}
          disconnected={ws.disconnected}
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
