# Session state (picked up 2026-09-05)

## Project
Covenant Certificate. Track 2 hack entry. Borrower-side loan-rule report helper.
Repo: https://github.com/MohitGoyal09/ao-hack.git

## Decisions made
- Production pipeline first, demo polish later.
- Demo will run on the real papers in `data/raw/`, not only hand-typed cases.
- LLMs go through LiteLLM gateway on Gemini only.
  Fast alias `covenant-fast` = `gemini/gemini-2.5-flash`.
  Strong alias `covenant-strong` = `gemini/gemini-2.5-pro`.
  Single key: `GEMINI_API_KEY`. Agent talks to the gateway in OpenAI-compatible
  form, so `apps/api/src/agent.py` needed no change.

## Done and tested in code
- Fixed money math (`src/covenant/calculator.py`). Decimal rounding, no eval,
  no model-written verdict. Tested: 3.14 pass, 4.17 breach, amendment 4.25.
- Strict checker (`src/covenant/policy.py`). Blocks on missing facts, unclear
  controlling paper, missing clause proof, unnamed or reason-free reviewer calls.
- Linked audit trail (`src/covenant/audit.py` + `hashing.py`). Hash-chained.
- LangGraph flow with 9 steps plus a plain sequential fallback for tests.
- Chat helper (`src/agent.py`). Two tools only: list cases, run calculator.
  Fixed offline script when no model key is set.
- Login plus file saving to Supabase, private bucket, access rules
  (`src/platform/supabase.py`, `supabase/migrations/202609050001_covenant_certificate.sql`).
- Redacted Neatlogs tracing (`src/platform/observability.py`). IDs only.
- Next.js thin UI (`apps/web/src/app/page.tsx`). Four practice cases, run,
  approve/reject buttons, proof list, clause list, trace list, CopilotChat.
- `docker-compose.yml`: litellm 4000, api 8123, web 3000.

## Main gaps (production work, in order)
1. Nothing reads real bank papers. All demo numbers are hand-typed in
   `src/covenant/catalog.py`. No PDF library in `apps/api/pyproject.toml`.
2. One rule checked per case. Other loan rules are skipped silently.
   Need a full rule list with skipped rules shown as skipped.
3. No memory of changes. A new paper must mark old answers outdated and
   expire old approvals. Missing: version records, revision APIs,
   stale-command 409 rejection, idempotency keys.
4. Agent cannot touch new documents. Only list plus run tools exist.
5. No locking sign-off tied to exact approved numbers.
6. Money travels as JSON floats. Contract wants exact strings.
7. Agent memory is in-RAM only (`MemorySaver`). No job queue with retries.
8. `data/gold/` and `data/derived/` are empty. `data/case-readiness.json`
   self-reports `full_verdict_not_ready`. No reviewed labels yet.
9. Stale pytest cache points at deleted `tests/test_covenant.py`.
   New suite (`test_covenant_workflow.py`, `test_main_api.py`,
   `test_platform.py`) still needs a green run with real deps.

## Next steps
1. Hand-enter one real loan rule plus matching numbers so a real answer
   flows through the same code.
2. Teach the backend to open that agreement file and pull the rule,
   with a person checking its work.
3. Add change memory (new paper expires old answers and approvals).
4. Add the full rule checklist.
5. Add the locking sign-off, then rebuild the demo on the real flow.

## Run and verify
- `docker compose up --build`, open http://localhost:3000, health at :8123.
- Backend: `cd apps/api && uv sync --frozen && uv run python -m unittest discover -s tests -v`
- Web: `cd apps/web && npm ci && npm run build`
- Model on: set `GEMINI_API_KEY` in `.env`. Persistence on: set Supabase vars
  and apply the migration. Everything stays runnable offline without them.
