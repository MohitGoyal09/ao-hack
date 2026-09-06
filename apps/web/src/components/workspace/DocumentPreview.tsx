"use client";

import { useEffect, useState } from "react";
import { apiBlob, DocumentMeta } from "@/lib/api";
import s from "./workspace.module.css";

export function DocumentPreview({ document, onClose }: { document: DocumentMeta; onClose: () => void }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let objectUrl = "";
    apiBlob(`/documents/${document.document_id}/content`)
      .then((blob) => { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); })
      .catch((reason: Error) => setError(reason.message));
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [document.document_id]);

  return <div className={s.previewBackdrop} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={s.previewDialog} role="dialog" aria-modal="true" aria-labelledby="document-preview-title">
      <header>
        <div><span>Source document</span><h2 id="document-preview-title">{document.title ?? document.document_id}</h2></div>
        <button type="button" onClick={onClose} aria-label="Close document preview">×</button>
      </header>
      <div className={s.previewMeta}><span>{(document.document_role ?? "document").replaceAll("_", " ")}</span><span>Version {document.version_number ?? 1}</span><span>{document.media_type ?? "file"}</span></div>
      {error ? <div className={s.previewState} role="alert">Preview unavailable: {error}</div> : url ? <iframe sandbox="" src={url} title={`Preview of ${document.title ?? "source document"}`} /> : <div className={s.previewState} aria-busy="true">Loading the authorized document…</div>}
    </section>
  </div>;
}
