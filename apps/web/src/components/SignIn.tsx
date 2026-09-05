"use client";

import { FormEvent, useState } from "react";
import { supabase } from "@/lib/supabase";
import { ROLES, Role, setOfflineIdentity, useIdentity, useOfflineIdentity } from "@/lib/api";
import styles from "@/app/page.module.css";

/** One small card: Supabase email/password sign-in (when configured) plus the offline identity selector. */
export function SignIn() {
  const identity = useIdentity();
  const offline = useOfflineIdentity();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true); setError("");
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    if (signInError) setError(signInError.message);
    setBusy(false);
  };

  if (identity.kind === "supabase") return <div className={styles.identity}>
    <p className={styles.cardKicker}>SIGNED IN</p>
    <strong>{identity.label}</strong>
    <span>Role <b>{identity.role}</b> (from app_metadata)</span>
    <button type="button" className={styles.secondaryButton} onClick={() => supabase?.auth.signOut()}>Sign out</button>
  </div>;

  return <div className={styles.identity}>
    {supabase && <form onSubmit={submit} className={styles.form}>
      <p className={styles.cardKicker}>SIGN IN</p>
      <label>Email <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <label>Password <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
      <button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      <p role="alert" aria-live="polite" className={styles.error}>{error}</p>
    </form>}
    <fieldset className={styles.form}>
      <legend className={styles.cardKicker}>OFFLINE IDENTITY{supabase ? " · used while signed out (offline API only)" : ""}</legend>
      <label>User <input value={offline.user} onChange={(e) => setOfflineIdentity({ ...offline, user: e.target.value })} /></label>
      <label>Role <select value={offline.role} onChange={(e) => setOfflineIdentity({ ...offline, role: e.target.value as Role })}>{ROLES.map((role) => <option key={role}>{role}</option>)}</select></label>
      <label>Org <input value={offline.org} onChange={(e) => setOfflineIdentity({ ...offline, org: e.target.value })} /></label>
      <span className={styles.muted}>Sends <code>Bearer {offline.user}:{offline.role}:{offline.org}</code></span>
    </fieldset>
  </div>;
}
