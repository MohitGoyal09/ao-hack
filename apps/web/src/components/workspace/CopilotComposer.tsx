"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { CopilotChat } from "@copilotkit/react-core/v2";
import { Attachments, Attachment, AttachmentInfo, AttachmentPreview, AttachmentRemove, PromptInput } from "@/components/ai-elements/attachments";
import { api, CaseSummary, createCase, UploadResult } from "@/lib/api";
import { canMutate, roleExplanation } from "@/lib/workflow";
import { clearTranscript, replaceTranscript } from "@/components/ai-elements/transcript";
import s from "./workspace.module.css";

type Props = { caseName?: string | null; caseId?: string | null; role?: string; templates?: CaseSummary[]; onCreated?: (caseId: string) => void; onUploaded?: (result: UploadResult) => Promise<void> };
const ACCEPTED_EXTENSIONS = new Set(["pdf", "json", "csv", "xlsx", "txt"]);
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const fileDetail = (file: File) => `${file.name.split(".").pop()?.toUpperCase() || "FILE"} · ${Math.max(1, Math.ceil(file.size / 1024))} KB`;

function CopilotTranscriptBridge({ messages, running }: { messages: any[]; running: boolean }) {
  useEffect(() => {
    replaceTranscript((messages ?? [])
      .filter((message: any) => ["user", "assistant", "tool"].includes(message.role))
      .filter((message: any) => message.role === "user" || message.role === "tool" || (typeof message.content === "string" && message.content.trim()))
      .map((message: any, index: number) => ({
        id: String(message.id ?? `${message.role}-${index}`),
        role: message.role,
        name: String(message.name ?? message.toolName ?? "Agent tool"),
        content: typeof message.content === "string" ? message.content.split("\n\n<!--attachment-context")[0] : "",
        status: running && index === messages.length - 1 && message.role === "assistant" ? "streaming" : "complete",
      })));
  }, [messages, running]);
  return null;
}

/** One docked prompt for chat and audited document intake. The local primitives
 * mirror AI Elements because this repo does not use its Tailwind/shadcn stack. */
export function CopilotComposer({ caseName, caseId = null, role = "viewer", templates = [], onCreated, onUploaded }: Props) {
  const uploadInput = useRef<HTMLInputElement>(null);
  const agentSubmit = useRef<((message: string) => Promise<void>) | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const mutate = canMutate(role);
  const isRoot = !caseId;
  useEffect(() => { clearTranscript(); }, [caseId]);

  const selectFile = (event: ChangeEvent<HTMLInputElement>) => {
    const next = event.target.files?.[0] ?? null;
    setError(""); setStatus("");
    if (!next) return;
    const extension = next.name.split(".").pop()?.toLowerCase() ?? "";
    if (!ACCEPTED_EXTENSIONS.has(extension)) { setFile(null); setError("Use a PDF, JSON, CSV, XLSX, or TXT file."); return; }
    if (next.size > MAX_UPLOAD_BYTES) { setFile(null); setError("This file is larger than the 50 MB upload limit."); return; }
    setFile(next);
    setStatus(`Attached ${next.name}. Press Enter to send.`);
    if (!templateId && templates[0]) setTemplateId(templates[0].id);
  };

  const uploadFile = async (selectedFile: File, userMessage: string) => {
    if (!selectedFile || !mutate) return;
    let targetCaseId = caseId;
    setBusy(true); setError(""); setStatus(isRoot ? "Creating a private case…" : "Uploading document…");
    try {
      if (!targetCaseId) {
        const starterId = templateId || templates[0]?.id;
        if (!starterId) throw new Error("Choose a prepared starter before uploading a document.");
        const created = await createCase({ template_case_id: starterId });
        targetCaseId = created.case_id;
        setStatus("Private case created. Uploading and starting intake…");
      }
      const body = new FormData();
      const lowerName = selectedFile.name.toLowerCase();
      const documentRole = lowerName.includes("amend") ? "amendment" : lowerName.includes("financial") || lowerName.includes("10-k") || lowerName.includes("statement") ? "financial_statement" : "credit_agreement";
      body.set("file", selectedFile);
      body.set("document_role", documentRole);
      body.set("title", selectedFile.name);
      const result = await api<UploadResult>(`/cases/${targetCaseId}/documents`, { method: "POST", body });
      setStatus(`Attached ${selectedFile.name}. The agent is deciding the next tool…`);
      await onUploaded?.(result);
      const agentKind = documentRole === "credit_agreement" || documentRole === "amendment"
        ? "agreement"
        : documentRole === "financial_statement" ? "financials" : documentRole;
      await agentSubmit.current?.(
        `${userMessage || `Process the attached ${selectedFile.name}.`}\n\n` +
        `<!--attachment-context I attached ${selectedFile.name} to private case ${targetCaseId}. ` +
        `Its stored document id is ${result.document_id}, revision ${result.revision_id}, ` +
        `and declared kind is ${agentKind}. Inspect the current case, choose the next ` +
        `authorized tool, and tell me what evidence is still required. -->`,
      );
      setFile(null);
      if (uploadInput.current) uploadInput.current.value = "";
      setStatus("");
      if (isRoot && targetCaseId) onCreated?.(targetCaseId);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : String(uploadError)); setStatus("");
    } finally { setBusy(false); }
  };

  return <div className={s.composer} aria-label="Treasury copilot">
    <CopilotChat
      threadId={caseId ? `covenant-${caseId}` : "covenant-start"}
      labels={{ chatInputPlaceholder: caseName ? `Ask about ${caseName}…` : "Ask about covenant review…" }}
      chatView={((chat: any) => {
        agentSubmit.current = async (message: string) => {
          await chat.onSubmitMessage?.(message);
          chat.onInputChange?.("");
        };
        const submit = async (event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          const text = String(chat.inputValue ?? "").trim();
          if (file) { await uploadFile(file, text); return; }
          if (!text || chat.isRunning) return;
          await chat.onSubmitMessage?.(text);
        };
        return <div className={s.composerInner}>
          <CopilotTranscriptBridge messages={chat.messages ?? []} running={Boolean(chat.isRunning)} />
          <form onSubmit={submit} className={s.promptForm} aria-label="Message and document intake">
            <input ref={uploadInput} type="file" accept=".pdf,.json,.csv,.xlsx,.txt" onChange={selectFile} hidden />
            <PromptInput><div className={s.promptDock}>
              {file && <div className={s.promptHeader}><Attachments variant="inline"><Attachment>
                <AttachmentPreview extension={file.name.split(".").pop()} /><AttachmentInfo name={file.name} detail={fileDetail(file)} />
                {!busy && <AttachmentRemove onClick={() => { setFile(null); setError(""); setStatus(""); if (uploadInput.current) uploadInput.current.value = ""; }} aria-label={`Remove ${file.name}`}>×</AttachmentRemove>}
              </Attachment>{isRoot && <label className={s.templatePick}>Prepared starter<select value={templateId} onChange={(event) => setTemplateId(event.target.value)} disabled={busy} aria-label="Prepared starter for upload"><option value="">Choose starter</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}</select></label>}</Attachments></div>}
              <div className={s.promptBody}>
                <textarea value={chat.inputValue ?? ""} onChange={(event) => { chat.onInputChange?.(event.target.value); event.currentTarget.style.height = "auto"; event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 140)}px`; }} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder={file ? "Add a note for this document (optional)" : caseName ? `Ask about ${caseName}…` : "Ask about covenant review…"} rows={1} aria-label="Message the treasury copilot" />
              </div>
              <div className={s.promptFooter}>
                <div className={s.promptTools}><button type="button" className={s.attachButton} onClick={() => uploadInput.current?.click()} disabled={busy || !mutate} aria-label={mutate ? "Add attachment" : "Document upload disabled"} title="Add attachment">＋</button>{file && <span>{busy ? "Uploading and sending to the agent…" : "Press Enter to send with your message."}</span>}</div>
                <button className={s.sendButton} type="submit" disabled={busy || chat.isRunning || (!file && !String(chat.inputValue ?? "").trim())} aria-label={file ? "Upload document and start processing" : "Send message"}>{busy ? "…" : "↑"}</button>
              </div>
            </div></PromptInput>
            {status && <p className={s.composerStatus} role="status">{status}</p>}
            {error && <p className={s.inlineError} role="alert">{error}</p>}
            {!mutate && <p className={s.gateNote} role="note">{roleExplanation("treasury_reviewer, officer or admin")} Document upload is disabled.</p>}
          </form>
        </div>;
      }) as any}
    />
  </div>;
}
