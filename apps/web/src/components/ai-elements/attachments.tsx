"use client";

import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import styles from "./attachments.module.css";

/**
 * A small, local implementation of the AI Elements attachment primitives.
 * The published components assume shadcn and Tailwind. This app uses CSS
 * modules and CopilotKit, so these preserve the same composable shape without
 * adding another chat runtime or a styling dependency.
 */
export function Attachments({ children, className = "", variant = "inline", ...props }: HTMLAttributes<HTMLDivElement> & { variant?: "inline" | "stack" }) {
  return <div className={`${styles.attachments} ${variant === "inline" ? styles.inline : styles.stack} ${className}`} {...props}>{children}</div>;
}

export function Attachment({ children, className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`${styles.attachment} ${className}`} {...props}>{children}</div>;
}

export function AttachmentPreview({ extension, className = "" }: { extension?: string; className?: string }) {
  return <span className={`${styles.preview} ${className}`} aria-hidden="true">{(extension || "file").slice(0, 4).toUpperCase()}</span>;
}

export function AttachmentInfo({ name, detail }: { name: string; detail: string }) {
  return <span className={styles.info} title={`${name} · ${detail}`}><strong>{name}</strong><small>{detail}</small></span>;
}

export function AttachmentRemove({ children = "Remove", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" className={`${styles.remove} ${className}`} {...props}>{children}</button>;
}

export function PromptInput({ children }: { children: ReactNode }) {
  return <div className={styles.promptInput}>{children}</div>;
}

export function Suggestion({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" className={styles.suggestion} {...props}>{children}</button>;
}
