# Demo video script — Covenant Certificate (target 3:30–4:30)

Devpost requires a public 3–5 minute video showing the core workflow end to
end, ease of use, and the AO dashboard with the total number of sessions. Record
at 1080p, browser zoom 110–125%, one take per beat, cut later. Speak the gist;
do not read the tables.

## Pre-flight (10 minutes, before recording)

1. Backend up and ready: `curl -s localhost:8123/health/ready` must return 200.
   - Hosted mode needs every migration applied (incl. the LangGraph checkpoint
     tables) and `python -m src.platform.worker` running in a second terminal.
   - Offline mode: start the API with the DB vars blanked
     (`DATABASE_URL= SUPABASE_URL= SUPABASE_SECRET_KEY= uv run uvicorn main:app --port 8123`);
     the in-process worker drains uploads. Pick the officer identity in the
     sign-in card (or set `DEMO_BEARER=demo-officer:officer:demo-org` in `apps/web/.env.local`).
2. `COPILOTKIT_TELEMETRY_DISABLED=true npm run dev` in `apps/web`.
3. Open `http://localhost:3000`, sign in (hosted) or pick the **officer**
   identity in the sign-in card, then confirm the **Start a new case** panel,
   the five curated template cards and the "Labelled hypothetical" tag on
   Aurora/Beacon. Delete nothing: every take creates its own case.
4. Have `data/raw/pdf-fixtures/aon-credit-agreement.pdf` in a file-picker-friendly folder.
5. Run the backend suite once in a terminal you can show at the end
   (`cd apps/api && uv run python -m unittest discover -s tests`).
6. Close anything showing `.env`, keys, or the Supabase dashboard secrets.
7. Have the AO dashboard open in another tab with the session list visible.

## Shot list

| t | Beat | On screen (exact actions) | Say (gist) |
|---|---|---|---|
| 0:00–0:15 | Problem | Title card: "Covenant Certificate — Track 2, Autonomous Office of the CFO" | Borrower treasury teams prepare covenant compliance certificates by hand. The credit agreement's definitions decide what debt and EBITDA mean, the period has to match, amendments move thresholds, and an officer signs. A mistake is an event of default. |
| 0:15–0:30 | Control principle | Landing page hero; hover the five template cards | The model proposes and calls tools; typed Python calculates; a human resolves evidence; an officer approves the exact draft. No LLM verdict, no `eval`. Everything is a marked draft — never a signed certificate. |
| 0:30–0:45 | Start a new case | Landing page, signed in as the officer. **Start a new case**: template **Aon term loan**, name "Aon Q1 2024 — demo take", Create → lands on `/cases/aon-q1-2024-demo-take-xxxx`. Snapshot shows `rev-1`; **Pipeline activity** shows only `#1 REVISION_CREATED`. | Every take starts clean: a fresh case at revision 1, created from a curated template under the signed-in organisation. Nothing from an earlier take leaks in. |
| 0:45–1:30 | Upload, durable job, live extraction | **Upload document**: choose `aon-credit-agreement.pdf`, role `credit_agreement`, title "Aon 2024 term loan", Upload. Point at the response: SHA-256, version 1, revision `rev-2`, job id. **Job timeline** chip goes queued → running → completed while **Pipeline activity** fills newest-first: `DOCUMENT_UPLOADED`, `RUN_STARTED`, `CALCULATION_COMPLETED` (ratio, threshold, 5 artifacts), `RUN_COMPLETED`. Snapshot panel: covenant rule "Section 6.14(b)" with threshold tiers and page citations; financial facts from the 10-K; artifacts list. Review inbox shows one blocking issue: **period mismatch** → status `NEEDS_REVIEW`. | One upload = one immutable hashed object, one document version, one revision, one durable job. A worker leases it with a fencing token and extracts the clause, its definitions and the threshold schedule from the real SEC exhibit with page citations. The activity feed is the durable event log itself, not an animation. Then the policy layer stops: the fiscal-2023 financials do not cover the Q1-2024 measurement period, so this is an extraction demo, not a compliance verdict for Aon. It asks for the right period instead of guessing. |
| 1:30–2:05 | Evidence-review pause and resolution | Back to `/`, click **Meridian evidence gap** → **Run**. Result: `NEEDS_REVIEW`, blocker "Supporting evidence and an authorized decision are required for Proposed restructuring add-back". **Review inbox**: decision `accept_evidence`, rationale "Board minutes and invoices reviewed 2026-09-06", Resolve. Snapshot: open issues 0. **Recalculate** → `DRAFT_COMPLIANT`, ratio 3.14 vs 3.50, cited clauses, evidence manifest with ✓ marks, hash-chained trace. | Missing support for an add-back never becomes zero and never becomes a pass. The run stops and asks a named reviewer for a reason. Every number, clause and decision lands in the trail. |
| 2:05–2:55 | Approve, amend, supersede, re-approve, download | **Officer approval**: reason "Reviewed draft Q4", Approve → locked summary: revision, ratio 3.14, threshold 3.50, `<=`, inputs, package hash. **Revision panel → Add amendment**: change kind `amendment`, new threshold `4.00`, Submit. Impact panel: changed definitions, stale artifacts, invalidated decision; approvals list now shows **SUPERSEDED** on the first approval; the feed shows `INPUT_CHANGED`, `RESULT_INVALIDATED`, `APPROVAL_RECORDED`. **Recalculate** → threshold 4.00. **Officer approval** again → new locked summary. (Optional 5 s: retry the old approval → 409 "stale".) **Download draft package** → JSON with approvals, hashes, citations. | An amendment creates a new revision; dependent results and the old approval are marked stale, never silently reused. The officer approves the exact numbers of the current draft — a replay against a superseded revision is rejected. Approval freezes a reviewed draft; it is not an e-signature. |
| 2:55–3:10 | Printable workpaper | Under the download button click **Open printable workpaper** → `/cases/meridian-evidence-gap/workpaper`: DRAFT banner, identification hashes, cited rule, exact facts, calculation, approvals with the **SUPERSEDED** stamp and the current one. Press **Print / Save as PDF**; show the print preview with the watermark on each page, then cancel. | The same snapshot as a document the officer can file: marked draft on every page, no pass/fail word on it, produced by the browser's print dialog. Not a signature, not delivery to a lender. |
| 3:10–3:25 | Two-agreement comparison — hypothetical | Landing page: **Aurora** card `DRAFT_COMPLIANT` 3.14 vs **Beacon** card `DRAFT_BREACH` 4.17, both tagged "Labelled hypothetical". | Same financial packet, two synthetic agreements, opposite result — the hard part is the definition, not the division. This is a labelled hypothetical, not a claim about any issuer. |
| 3:25–4:05 | How we used AO (mandatory) | Switch to the **AO dashboard**: total session count visible; scroll the session list; open one early research session and one build-phase session; show the repo's `docs/agent-handoff.md` that sessions used as their brief. | AO ran the whole build: parallel research sessions on covenant primary sources and domain design, planning sessions that wrote the backend/frontend plans and the handoff packet, one session per implementation phase (failing test → smallest slice → full suite → one commit), and two multi-agent audit-and-build waves with a shared notes directory as memory between agents. AO is a dev-time tool only; the product does not depend on it at runtime. |
| 4:05–4:25 | Close | Terminal: backend suite output (`OK`, with the count it prints) and `docs/evaluation.md` headline table; README "Limitations & non-claims"; repo URL; team names. | What is real: deterministic calculation, fail-closed review, Postgres-backed revisions and approvals, immutable intake, a fenced worker, a live event log, a review UI, a printable draft workpaper, a harness that reports every number with its denominator. What is not: no legal advice, no signed PDF, one agreement parser shape, no real-issuer verdict, no holdout set, no user validation yet. |

## What not to say or show

- Do not read numbers from `docs/evaluation.md` as accuracy claims: "3/3 supported labels, 7/10 unsupported, 0/15 false passes" are observed results on a small curated set.
- Never show "Aon … Draft compliant". The Aon case must read `NEEDS_REVIEW` (period mismatch). If it does not, stop and fix before recording.
- Do not call the output a certificate, a signature, or compliance with the agreement. Say "draft", "leverage test", "officer-approved draft package".
- Do not claim LLM extraction. Extraction is deterministic Python (pdfplumber + fixed patterns) for the Aon shape; the model only proposes and calls tools, and only when a key is set.
- Do not claim Neatlogs traces unless a real Neatlogs dashboard is on screen.
- Do not claim accuracy numbers, holdout results, or user validation. "Zero false passes on the curated set" is an observed result on a small set.
- Do not show `.env`, keys, the Supabase secret key, or the database password.
- Do not present Aurora/Beacon/Meridian as real companies.

## If something breaks on camera

- Upload stuck at `queued`: worker is not running (hosted) or `INPROCESS_WORKER` is `0` (offline). Restart, re-record the beat.
- 401 in the UI: no bearer — sign in, or set `DEMO_BEARER` and restart `next dev`.
- **Start a new case** returns 403: the identity is a `viewer`; pick the officer or reviewer.
- **Pipeline activity** looks stale: it polls every 2 s while a job runs and every 10 s otherwise; a red fetch error there means the bearer expired — sign in again.
- 503 on every route: `/health/ready` is failing; check the checkpoint migration or run offline.
- 409 on resolve/approve: the snapshot changed underneath — refresh and redo; this is the product working, say so if it happens.
