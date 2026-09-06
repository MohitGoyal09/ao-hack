"use client";

import { useSyncExternalStore } from "react";

export type TranscriptMessage = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  name?: string;
  status?: "streaming" | "complete" | "error";
};

let messages: TranscriptMessage[] = [];
const EMPTY_TRANSCRIPT: TranscriptMessage[] = [];
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((listener) => listener());

/** A tiny external store keeps the CopilotKit composer and the transcript
 * decoupled without adding a global state dependency. */
export function replaceTranscript(next: TranscriptMessage[]) {
  const normalized: TranscriptMessage[] = next.map((message, index) => ({
    id: String(message.id ?? `${message.role}-${index}`),
    role: (message.role === "user" || message.role === "tool" ? message.role : "assistant") as TranscriptMessage["role"],
    content: typeof message.content === "string" ? message.content : "Working with the covenant record.",
    name: message.name,
    status: message.status,
  }));
  const visibleUserContent = new Set(normalized.filter((item) => item.role === "user").map((item) => item.content));
  const optimistic = messages.filter((item) => item.id.startsWith("pending-upload-") && !visibleUserContent.has(item.content));
  const merged = [...optimistic, ...normalized];
  if (JSON.stringify(messages) === JSON.stringify(merged)) return;
  messages = merged;
  emit();
}

export function appendTranscript(message: TranscriptMessage) {
  messages = [...messages.filter((item) => item.id !== message.id), message];
  emit();
}

export function clearTranscript() {
  if (!messages.length) return;
  messages = [];
  emit();
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
const snapshot = () => messages;

export function useTranscript() {
  return useSyncExternalStore(subscribe, snapshot, () => EMPTY_TRANSCRIPT);
}
