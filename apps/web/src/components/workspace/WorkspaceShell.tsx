"use client";

import { useEffect, useState } from "react";
import s from "./workspace.module.css";

function useNarrow() {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 1023px)");
    const update = () => setNarrow(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return narrow;
}

export function WorkspaceShell({ rail, main, context, composer, contextCollapsed = false }: { rail: React.ReactNode; main: React.ReactNode; context: React.ReactNode; composer?: React.ReactNode; contextCollapsed?: boolean }) {
  const narrow = useNarrow();
  if (narrow) {
    return (
      <main className={s.desktopGate}>
        <div>
          <p className={s.kicker}>Covenant Certificate · Office of the CFO</p>
          <h1>Open on a desktop</h1>
          <p>This covenant workbench needs conversation, evidence, calculation and review side by side. Reopen it at 1024 px or wider (best at 1440 px).</p>
        </div>
      </main>
    );
  }
  return (
    <main className={s.shell} data-context-collapsed={contextCollapsed ? "true" : "false"}>
      <a className={s.skipLink} href="#conversation">Skip to conversation</a>
      {rail}
      <div className={s.center}>
        <div className={s.conversation} id="conversation" tabIndex={-1}>
          <div className={s.conversationInner}>{main}</div>
        </div>
        {composer}
      </div>
      {context}
    </main>
  );
}

/** Scroll to a conversation card without smooth scrolling (no scroll warnings). */
export function scrollToCard(anchorId: string) {
  document.getElementById(anchorId)?.scrollIntoView({ block: "start" });
}
