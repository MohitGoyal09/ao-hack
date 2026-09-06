"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, Job, Revision, Snapshot, TERMINAL_JOB_STATES, useIdentity } from "@/lib/api";
import type { DomainEvent } from "@/components/EventFeed";

// One polling hook for the whole workspace: snapshot + jobs + durable
// events, driven by persisted backend state only.
export function useCaseWorkspace(caseId: string | null) {
  const identity = useIdentity();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [events, setEvents] = useState<DomainEvent[]>([]);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [error, setError] = useState("");
  const [disconnected, setDisconnected] = useState(false);
  const seqRef = useRef(0);

  const refresh = useCallback(async () => {
    if (!caseId) return;
    try {
      const [snap, jobList] = await Promise.all([
        api<Snapshot>(`/cases/${caseId}/snapshot`),
        api<Job[]>(`/cases/${caseId}/jobs`),
      ]);
      setSnapshot(snap);
      setJobs(jobList);
      setError("");
      setDisconnected(false);
      setRevisions((prev) => {
        if (snap.revisions) return snap.revisions;
        return prev.some((r) => r.revision_id === snap.revision.revision_id) ? prev : [...prev, snap.revision];
      });
      // Event gap recovery: reload from the last durable sequence we kept.
      try {
        const fresh = await api<DomainEvent[]>(`/cases/${caseId}/events?after_sequence=${seqRef.current}&limit=200`);
        if (fresh.length) {
          seqRef.current = fresh[fresh.length - 1].sequence;
          setEvents((prev) => {
            const known = new Set(prev.map((e) => e.sequence));
            return [...prev, ...fresh.filter((e) => !known.has(e.sequence))];
          });
        }
      } catch {
        // Snapshot is authoritative; a failed event poll keeps the last snapshot.
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      if (message.startsWith("503") || message.includes("unavailable") || message.includes("Failed to fetch")) setDisconnected(true);
    }
  }, [caseId]);

  const who = `${identity.kind}:${identity.label}:${identity.role}`;
  useEffect(() => {
    seqRef.current = 0;
    setEvents([]);
    setSnapshot(null);
    setRevisions([]);
    if (caseId) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, who]);

  const active = jobs.some((j) => !TERMINAL_JOB_STATES.has(j.state)) || snapshot?.run_state === "running" || snapshot?.run_state === "queued";
  useEffect(() => {
    if (!caseId) return;
    const timer = setInterval(refresh, active ? 500 : 10000);
    return () => clearInterval(timer);
  }, [caseId, active, refresh]);

  return { snapshot, jobs, events, revisions, error, disconnected, active, refresh };
}
