# Agent handoff (written 2026-09-05, base commit 858431e)

## Start here
1. Read `docs/implementation-contract.md` first. It overrules older plans.
2. Read `docs/session-state.md` for decisions so far.
3. Read this file for where the build stands and what to do next.
4. Code entry points: `apps/api/main.py`, `apps/api/src/agent.py`,
   `apps/api/src/covenant/` (domain, catalog, ingestion, calculator,
   policy, orchestration, revisions, evidence, certificate, audit),
   `apps/api/src/platform/` (supabase, observability).

## Repo facts
- Branch `main`, worktree clean at handoff time. Push before starting.
- Backend owns all decisions. `apps/web` is display only.
- Gateway models are Gemini only: `covenant-fast` = gemini-2.5-flash,
  `covenant-strong` = gemini-2.5-pro, single key `GEMINI_API_KEY`.
- `apps/api/litellm/` and `apps/api/supabase/` live inside the backend.
  Run `supabase` CLI commands from inside `apps/api`.
- Supabase migration: `apps/api/supabase/migrations/202609050001_covenant_certificate.sql`.

## Verified state
- Backend suite 25/25 green (`test_agent` 4, `test_covenant_workflow` 13,
  `test_main_api` 5, `test_platform` 3). Catalog holds 5 cases including
  the real `aon-term-loan-leverage` case read from the PDF plus 10-K.
- LangGraph workflow is a real 9-node graph with a sequential test fallback.
- Agent exposes 4 tools: list cases, run calculator, ingest document,
  re-run case. Offline script answers when no model key is set.
- Revision APIs exist and are tested: create revision, impact, review-resolve
  with stale-command rejection, officer approval bound to revision plus
  package hash, snapshot. Store is in-memory only.
- Money serializes as exact decimal strings. Full rule checklist with
  explicit coverage (skipped rules shown, never passed silently).

## Current gaps, in build order
1. Revision store is in-memory. Restarts wipe version history. Back it with
   Supabase/Postgres with leases before any durability claim.
2. No document upload endpoint. Agent ingest takes a server-side path only.
3. No live AG-UI event stream. Zero of the 14 contract events
   (RUN_STARTED, TOOL_CALL_*, EVIDENCE_FOUND, CALCULATION_COMPLETED,
   REVIEW_REQUIRED, RESULT_INVALIDATED, PACKAGE_REVISED, RUN_COMPLETED,
   RUN_FAILED, and the rest) are emitted. Trace is post-hoc in the payload.
4. Agent memory is `MemorySaver` (in-RAM). No job queue with retries.
5. No reviewed labels. `data/gold/` and `data/derived/` are empty.
6. No untouched agreement family for the final holdout test.
7. Gemini path never ran with a real key. No gateway contract test.
8. No signed-PDF rendering (allowed to stay out; export stays a marked
   incomplete workpaper).

## Limitation plans (hard rules for the next session)
- Never present an AI result as a signed certificate or legal conclusion.
  Every verdict stays a draft needing an authorized officer.
- The two-agreement comparison is a labelled hypothetical. The contracts do
  not govern the same borrower and period, so never report it as a real
  breach by either company.
- The Aon case pairs a Feb 2024 agreement and Mar 2024 test date with
  FY2023 figures. Treat it as an ingestion and plumbing proof, not a real
  compliance verdict. Record period mismatches explicitly per case.
- Controlled modifications and withheld evidence are labelled synthetic or
  intentionally incomplete, never real issuer findings.
- In-memory stores (revisions, agent checkpoints) must not be described as
  durable. Do not claim restart recovery until it is tested.
- Zero false passes on a tiny dataset is an observed result, not proof of
  production safety. Report test counts with denominators.
- Keep credentials out of the repo. `.env` only, never committed.

## Environment quirks
- This checkout lives outside the helper's default writable area, so file
  writes need explicit per-command approval. Batch them.
- The home uv cache can be permission-blocked. If `uv sync` fails on
  `/Users/mohit/.cache/uv`, retry with
  `UV_CACHE_DIR=/tmp/uv-cache-ao uv sync --frozen`.
- After any dependency change, re-sync the venv or the whole suite fails on
  import (seen already with pdfplumber).
- Commits are authored solely by the human developer. No AI co-author
  trailers in messages or PR bodies.

## Next session packet
1. Back the revision store with Supabase. Acceptance: restart the API,
   history and approvals survive, stale-command rejection still 409s.
2. Add the document upload endpoint writing to the private bucket with
   hashes. Acceptance: upload, hash recorded, case references it.
3. Emit the live event stream with call IDs and redacted summaries.
   Acceptance: UI shows node and tool progress during a run.
4. Create reviewed extraction labels for the Aon case under
   `data/annotations/` (PROPOSED) and promote only after review to
   `data/gold/` with reviewer identity, date, rationale, and source spans.
5. Acquire one untouched agreement family for holdout. Never train or tune
   prompts against it; evaluation only.
6. Run the first real Gemini smoke test with `GEMINI_API_KEY` set and
   record model, prompt version, and input hash per the contract.
7. Update this handoff plus `docs/session-state.md` and commit when done.

## Implementation plans and their standing
- Controlling spec is `docs/implementation-contract.md`. It overrules both
  plans below wherever they conflict.
- Main backend plan: `docs/superpowers/plans/2026-09-04-covenant-certificate-backend.md`.
  16 tasks (0 to 15): document readiness, demo replacement, Supabase schema,
  Auth plus Storage, document intake, precedence, definition graphs, fact
  extraction, calculation engine, review plus changed-input invalidation,
  LangGraph with Postgres checkpoints, authenticated APIs plus AG-UI events,
  certificate rendering, Neatlogs, gold eval harness, completion gate.
  Standing: Tasks 5-9A exist in working form but in-memory, not on Postgres.
  Tasks 0, 4, 10-11 (durable parts), 14-15 are open.
- Frontend plan: `docs/superpowers/plans/2026-09-05-covenant-certificate-frontend.md`.
  10 tasks: design system, shell plus navigation, case creation plus intake,
  AG-UI state plus domain events, definition workbench, evidence plus
  calculation views, review interrupts, change-and-recheck demo, certificate
  preview, accessibility plus QA. Standing: demo slice done (run, evidence,
  clauses, trace, chat); intake, live events, revision comparison open.
- Known plan drift, follow the built code: plan paths say
  `apps/api/src/covenant_certificate/`, code uses `apps/api/src/covenant/`.
  Plan names Docling, code uses pdfplumber. Plan names SQLAlchemy plus
  psycopg, code uses supabase-py with an in-memory store. Plan names pytest,
  Ruff, mypy; code runs unittest with no lint or type gate yet.

## Run and verify
- `docker compose up --build`; UI http://localhost:3000, API :8123/health.
- Backend: `cd apps/api && uv sync --frozen && uv run python -m unittest discover -s tests -v`
- Web: `cd apps/web && npm ci && npm run build`
