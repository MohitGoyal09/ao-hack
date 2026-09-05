"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./supabase";

// ---------- types (shapes from apps/api/main.py; fields marked ? are optional snapshot additions) ----------
export type CaseSummary = { id: string; name: string; narrative: string; agreement: string; agreement_version: string; test_date: string; scenario_type: string; covenant_name?: string };
// /run carries exact two-decimal strings (money_str); older builds sent floats. Always format via num()/fix().
export type Num = number | string;
export type Calculation = { formula: string; numerator: Num; denominator: Num; ratio: Num; threshold: Num; comparator: string; headroom: Num; original_threshold?: Num | null };
export const num = (value: Num) => Number(value);
export const fix = (value: Num) => Number(value).toFixed(2);
export type RunResult = {
  status: "DRAFT_COMPLIANT" | "DRAFT_BREACH" | "NEEDS_REVIEW";
  status_reason: string;
  run_id?: string;
  case: CaseSummary;
  calculation: Calculation;
  citations: { document: string; locator: string; excerpt: string }[];
  evidence: { label: string; value: string; source: string; supported: boolean }[];
  blocking_issues: string[];
  trace: { step: string; label: string; detail: string }[];
  certificate: { draft_mark: string; agreement: string; agreement_version: string; test_date: string; result: string; finalization_allowed: boolean; generated_at: string };
  covenant_results?: unknown;
  coverage?: unknown;
};
export type Revision = { case_id: string; revision_id: string; parent_revision: string | null; test_date: string; input_bundle_hash: string; rulebook_hash: string; mapping_hash: string; calculation_hash: string; coverage_hash: string; package_hash: string; status: string; threshold: string; rule_id: string; change_kind?: string };
export type Approval = { actor: string; role: string; target_revision: string; bundle_hash: string; package_hash: string; decision: string; reason: string; timestamp: string; superseded: boolean; approved_ratio: string | null; approved_threshold: string | null; approved_comparator: string | null; approved_inputs: Record<string, string>; locked_summary?: string };
// Worker calculation artifact (snapshot.artifacts.calculation): exact decimal strings the officer approval must echo back verbatim.
export type CalculationArtifact = { ratio: string; threshold: string; comparator: string; inputs: Record<string, string>; period_check?: { matches: boolean; facts_period_end: string; measurement_period_end: string; note?: string } };
export type ReviewIssue = { issue_id: string; revision_id?: string; status: string; kind?: string; summary?: string; decision_kind?: string | null; rationale?: string | null; evidence_refs?: string[]; resolved_by?: string | null };
export type Job = { job_id: string; revision_id: string; state: string; attempt_count: number; fencing_token?: number | null; lease_owner?: string | null; last_error: string | null };
export type Snapshot = {
  case_id: string; revision: Revision; run_state: string;
  per_covenant_results: { rule_id: string; threshold: string; status: string }[];
  coverage: { state: string; hash: string }; package_state: string; package_hash: string;
  open_review_issues: number; documents: unknown[]; approvals: Approval[]; last_event_sequence: number; organization_id?: string | null;
  review_issues?: ReviewIssue[]; artifacts?: { calculation?: CalculationArtifact } & Record<string, unknown>; financial_facts?: unknown; covenant_rules?: unknown; revisions?: Revision[];
};
export type UploadResult = { document_id: string; version_id: string; version_number: number; sha256: string; extraction_state: string; revision_id: string; job_id: string };
// GET /cases (member-scoped) and POST /cases (fresh case from a catalog template).
export type CaseListItem = { case_id: string; name: string; template_case_id: string | null; test_date: string | null; created_at: string | null; run_state: string | null };
export type CreatedCase = { case_id: string; organization_id: string; template_case_id: string; name: string };
export type RevisionResult = { revision_id: string; revision: Revision; changeset: Record<string, unknown>; impact_pending: Record<string, string[]> };
export type ImpactResult = { revision_id: string; changed_inputs: string[]; affected_rule_ids: string[]; stale_artifact_ids: string[]; review_requirements: string[]; impact: Record<string, string[]> };

export const TERMINAL_JOB_STATES = new Set(["completed", "failed", "cancelled"]);
export const OFFICER_ROLES = new Set(["officer", "admin"]);
// snapshot.documents is a list of ids today; tolerate objects once intake becomes append-only.
export const docId = (doc: unknown): string => typeof doc === "string" ? doc : String((doc as { document_id?: string; id?: string })?.document_id ?? (doc as { id?: string })?.id ?? JSON.stringify(doc));
export const short = (hash: string | null | undefined) => (hash ? `${hash.slice(0, 12)}…` : "—");

// ---------- offline identity: `Bearer <user>:<role>:<org>` accepted by the API in offline mode ----------
export type Role = "viewer" | "treasury_reviewer" | "officer" | "admin";
export const ROLES: Role[] = ["viewer", "treasury_reviewer", "officer", "admin"];
export type Identity = { user: string; role: Role; org: string };
const KEY = "covenant.offlineIdentity";
const DEFAULT_IDENTITY: Identity = { user: "demo-officer", role: "officer", org: "demo-org" };
const listeners = new Set<() => void>();
let cached: Identity | null = null;
export function getOfflineIdentity(): Identity {
  if (cached) return cached;
  try { cached = JSON.parse(localStorage.getItem(KEY) ?? "") as Identity; } catch { cached = DEFAULT_IDENTITY; }
  return cached;
}
export function setOfflineIdentity(identity: Identity) {
  cached = identity;
  try { localStorage.setItem(KEY, JSON.stringify(identity)); } catch { /* private mode */ }
  listeners.forEach((listener) => listener());
}
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export const useOfflineIdentity = () => useSyncExternalStore(subscribe, getOfflineIdentity, () => DEFAULT_IDENTITY);

export function useSession() {
  const [session, setSession] = useState<Session | null>(null);
  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => data.subscription.unsubscribe();
  }, []);
  return session;
}

/** Who the API will see: the Supabase session when signed in, else the offline identity. */
export function useIdentity() {
  const session = useSession();
  const offline = useOfflineIdentity();
  return session
    ? { kind: "supabase" as const, label: session.user.email ?? session.user.id, role: String(session.user.app_metadata?.role ?? "none"), session }
    : { kind: "offline" as const, label: offline.user, role: offline.role, session: null };
}

// ---------- fetch wrapper ----------
export class ApiError extends Error {
  constructor(public status: number, public detail: string) { super(`${status} — ${detail}`); }
}

async function bearer() {
  if (supabase) {
    const { data } = await supabase.auth.getSession();
    if (data.session) return `Bearer ${data.session.access_token}`;
  }
  const { user, role, org } = getOfflineIdentity();
  return `Bearer ${user}:${role}:${org}`;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("authorization", await bearer());
  if (init.body && !(init.body instanceof FormData)) headers.set("content-type", "application/json");
  const response = await fetch(`/api/covenant${path}`, { ...init, headers, cache: "no-store" });
  const text = await response.text();
  let data: unknown = text;
  try { data = text ? JSON.parse(text) : null; } catch { /* non-JSON body */ }
  if (!response.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(response.status, typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : response.statusText);
  }
  return data as T;
}
export const post = <T,>(path: string, body: unknown) => api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const listCases = () => api<CaseListItem[]>("/cases");
export const createCase = (body: { template_case_id: string; name?: string; test_date?: string }) => post<CreatedCase>("/cases", body);

/** busy + error state around one mutation; a 409 refreshes the caller's state and says so. */
export function useAction(onStale?: () => Promise<void>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await fn(); }
    catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(err instanceof ApiError && err.status === 409 ? `Stale — state changed underneath you; panel refreshed. ${message}` : message);
      if (err instanceof ApiError && err.status === 409) await onStale?.();
    } finally { setBusy(false); }
  }, [onStale]);
  return { run, busy, error };
}
