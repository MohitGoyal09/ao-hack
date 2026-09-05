# Covenant Certificate — agent instructions

Track 2 (Autonomous Office of the CFO) hackathon entry: an evidence-first
workflow that prepares an officer-reviewed *draft* loan-covenant compliance
certificate. Upload agreement + financials -> extract and cite the rule ->
deterministic Decimal calculation -> human review when evidence is missing ->
amendment creates a revision -> officer approves the exact locked numbers.
Never legal advice, never a signed certificate.

## Source of truth (highest first)
1. Current code (`apps/api`, `apps/web`).
2. `docs/implementation-contract.md`.
3. `docs/agent-handoff.md` (phases, status, limits).
4. Older plans in `docs/superpowers/plans/` and `docs/session-state.md`.

## Before you start
- Read `agent-docs/` first (local-only shared memory between agents: audits,
  checklist, build notes). Update it as you work, not just at the end.
- `agent-docs/` is in `.git/info/exclude`. Never `git add` it.

## Run and test
```bash
cd apps/api && uv sync --frozen && uv run python -m unittest discover -s tests   # 142 OK / 13 skipped (2026-09-06); test__env.py blanks DB + LLM vars
cd apps/api && uv run uvicorn main:app --port 8123                               # offline unless root .env has DATABASE_URL
cd apps/api && uv run python -m src.platform.worker                              # Postgres mode only
cd apps/web && npm ci && npm run build                                           # or npm run dev
docker compose up --build                                                        # litellm, api, worker, web
git diff --check
```
- A filled root `.env` puts uvicorn in hosted mode; force offline with
  `DATABASE_URL= SUPABASE_URL= SUPABASE_SECRET_KEY= uv run uvicorn main:app`.
  `LITELLM_API_KEY=` blanks the live model (deterministic chat graph).
- Running a single test module (`-m unittest tests.test_ag_ui`) bypasses
  `tests/test__env.py`, so the live `LITELLM_API_KEY` from `.env` leaks in and
  LLM-phrasing assertions fail. Run the whole suite, or prefix `LITELLM_API_KEY=`.
- Snapshot JSON contract (keys, `run_state`/`package_state` machine,
  `artifacts.calculation` exact strings the officer approval echoes back):
  `agent-docs/build-b-pipeline-snapshot.md`. Offline UI story:
  `agent-docs/integration.md`.
- Live model: NVIDIA NIM `nvidia/nemotron-3-super-120b-a12b` via
  `LITELLM_BASE_URL`/`LITELLM_API_KEY`/`LITELLM_STRONG_ALIAS` (see
  `agent-docs/build-e-model.md`); `LITELLM_FAST_ALIAS` is unused by the API.
- `COVENANT_TEST_KEEP_ENV=1` keeps the real env for the `TEST_DATABASE_URL`
  integration test (isolated DB only).
- Offline bearer: `Authorization: Bearer user:role:org`
  (roles `viewer|treasury_reviewer|officer|admin`, org `demo-org`).
- Port 8123 is shared between agents; pick another port if it is busy.

## Safety rules
- Hosted Supabase (`ao-hack`) is shared: no `db reset`, `db push` without
  team approval, TRUNCATE/DROP/DELETE, or ad-hoc DDL. Add forward-only
  migrations via `supabase migration new`; never edit an applied one.
- Secrets only in the git-ignored root `.env`. Never commit `.env`,
  `apps/web/.env.local`, or `agent-docs/`. Never paste keys into docs or chat.
- The LLM is never authoritative: it may propose facts/rules and call typed
  tools; it never calculates, accepts evidence, approves, or signs. Missing or
  unclear evidence never becomes zero or a pass.
- Configured-but-broken durability must fail readiness, never fall back to
  memory. Memory mode only when no `DATABASE_URL` is set.
- Label synthetic comparisons "hypothetical"; the Aon case is extraction only
  (period mismatch -> `NEEDS_REVIEW`), never a compliance verdict.
- No destructive git (reset --hard, force-push, history rewrite). Commit and
  push only when asked.

## Parallel-agent file ownership
- Backend durability/worker: `apps/api/src/platform/`, `apps/api/supabase/`,
  `docker-compose.yml`, `apps/api/Dockerfile`.
- Backend pipeline/policy/snapshot: `apps/api/src/covenant/`, `apps/api/main.py`
  (coordinate: main.py is shared).
- Frontend: `apps/web/`. Routes `/` and `/cases/[id]` (workbench); all API
  calls go through `src/lib/api.ts` → same-origin proxy
  `src/app/api/covenant/[...path]/route.ts` (forwards `Authorization` and
  multipart; `AGENT_URL` picks the API). Plain React + `page.module.css`, no UI
  libs. One `next dev` per checkout (`.next/dev` lock). `/run` returns
  exact-decimal strings — format with `Number()`. See `agent-docs/build-c-frontend.md`.
- Docs/data/scripts/env examples: `README.md`, `docs/`, `data/`, `scripts/`,
  `.env.example`, `config/team/`, this file.
- Tests live next to their owner in `apps/api/tests/`. Never two agents in
  the same migration, API model, or event schema at once.
- Each agent documents its work in `agent-docs/<name>.md` and adds a row to
  `agent-docs/README.md` (re-read before appending).

## Docs discipline
- Fix stale claims when you see them (routes, counts, migrations). Prefer
  "the suite prints the count" over hard-coded numbers.
- Mark anything you have not run yourself with `<!-- VERIFY -->` in Markdown.
- Update `docs/agent-handoff.md` after each phase: commit, checks, limits.
