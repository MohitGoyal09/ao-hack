"use client";

import { Dispatch, SetStateAction, useEffect, useState } from "react";

/** Keep workspace-only display preferences without making them authoritative state. */
export function useWorkspacePreference<T>(key: string, fallback: T): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(fallback);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(key);
      if (stored != null) setValue(JSON.parse(stored) as T);
    } catch {
      // A blocked or malformed preference must not stop a finance workflow.
    } finally {
      setLoaded(true);
    }
  }, [key]);

  useEffect(() => {
    if (!loaded) return;
    try { window.localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ }
  }, [key, loaded, value]);

  return [value, setValue];
}
