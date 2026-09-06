"use client";

import type { StageState } from "@/lib/workflow";
import s from "./workspace.module.css";

// Status is never color-alone: every badge carries an icon glyph + text.
const GLYPH: Record<string, string> = {
  pending: "○",
  running: "◐",
  blocked: "◍",
  complete: "●",
  failed: "✕",
  stale: "◌",
  queued: "○",
  waiting_review: "◍",
  completed: "●",
  cancelled: "✕",
  pass: "●",
  fail: "✕",
  indeterminate: "◍",
  open: "◍",
  resolved: "●",
  approved: "●",
  superseded: "◌",
};

const TONE: Record<string, string> = {
  pending: s.toneNeutral,
  running: s.toneRunning,
  blocked: s.toneReview,
  complete: s.toneGood,
  failed: s.toneBad,
  stale: s.toneStale,
  queued: s.toneNeutral,
  waiting_review: s.toneReview,
  completed: s.toneGood,
  cancelled: s.toneStale,
};

export function toneFor(state: string): string {
  const key = state.toLowerCase();
  if (TONE[key]) return TONE[key];
  if (key.includes("breach") || key.includes("fail") || key.includes("reject")) return s.toneBad;
  if (key.includes("review") || key.includes("warn") || key.includes("request")) return s.toneReview;
  if (key.includes("pass") || key.includes("compliant") || key.includes("approv") || key.includes("ready")) return s.toneGood;
  if (key.includes("stale") || key.includes("superseded") || key.includes("cancel")) return s.toneStale;
  if (key.includes("run") || key.includes("progress") || key.includes("recalc")) return s.toneRunning;
  return s.toneNeutral;
}

export function StatusBadge({ state, label }: { state: StageState | string; label?: string }) {
  const text = label ?? String(state).replace(/_/g, " ");
  const glyph = GLYPH[String(state).toLowerCase()] ?? "○";
  return (
    <span className={`${s.badge} ${toneFor(String(state))}`}>
      <span aria-hidden="true" className={s.glyph}>{glyph}</span> {text}
    </span>
  );
}
