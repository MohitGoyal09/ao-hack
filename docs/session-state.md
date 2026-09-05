# Session state (updated 2026-09-06)

Short pointer file. `docs/agent-handoff.md` is the execution packet and wins
over this file; current code wins over both.

## Project
Covenant Certificate. Track 2 hack entry. Borrower-side loan-covenant
compliance-certificate draft helper with human review and officer approval.
Repo: https://github.com/MohitGoyal09/ao-hack.git

## Decisions made
- Production pipeline first, demo polish later.
- One real-source case (Aon) exists for extraction; its period mismatch means
  it is a `NEEDS_REVIEW` extraction demo, never a verdict. Other cases are
  synthetic; the two-agreement comparison is a labelled hypothetical.
- Model access is any OpenAI-compatible endpoint (`LITELLM_BASE_URL`,
  `LITELLM_API_KEY`, `LITELLM_STRONG_ALIAS`): NVIDIA NIM directly, or Gemini
  through the optional LiteLLM proxy. No key = offline deterministic graph.
- The model never calculates, accepts evidence, approves, or signs.

## Done (see handoff "What is implemented" and "2026-09-06 build session")
- Decimal calculator, fail-closed policy (incl. period mismatch), hash-chained
  trace, 9-node LangGraph, full rule checklist with explicit coverage.
- Aon PDF + 10-K extraction with page/section citations.
- Revisions, impact, stale-command 409s, idempotency, officer approval locked
  to exact numbers; Postgres repository when `DATABASE_URL` is set.
- Authenticated immutable document intake (object + version + revision +
  event + job); durable job queue with fencing; worker + case pipeline.
- Fail-closed durability readiness; LangGraph checkpoint migration.
- 10 reviewed extraction-only gold labels with dataset-gate tests.
- `/cases/[id]` workbench (sign-in, upload, jobs, review, revisions,
  approval, download); production build passes.

## Main gaps (current)
1. No durable LangGraph `interrupt`/resume: review is REST state, not a
   paused graph execution that survives restart (Phase 5).
2. Live model proof is a single observed session (2026-09-06, NVIDIA NIM
   `nvidia/nemotron-3-super-120b-a12b`: list -> run -> 3.14x matching the
   calculator, directly and over `/ag-ui`); no automated test covers it, and
   the offline deterministic graph is what runs without a key.
3. No event outbox / AG-UI replay: the UI polls `jobs` and `snapshot`
   (Phase 6).
4. Parser covers one agreement shape (Aon); everything else is `unsupported`
   or `needs_ocr`. No OCR.
5. No holdout agreement family; false-pass count is on the curated set only
   (Phase 8).
6. Export is a JSON draft package; no marked PDF workpaper (Phase 9).
7. Neatlogs wired but never exercised with a key.
8. npm audit: 18 transitive findings (0 critical) untriaged.
9. No case-creation API; demo cases are seeded per organization on first
   snapshot read. No user/org seed script (manual Auth admin + SQL inserts).

## Next steps
1. Push the 2026-09-06 build-session commits; record the demo video from
   `docs/demo-script.md`.
2. (done) Checkpoint migration applied to hosted; `/health/ready` 200 and
   `/ag-ui` mounted, verified 2026-09-06.
3. Record the demo (`docs/demo-script.md`) with the AO dashboard shot.
4. Optional before recording: one live NIM tool-calling run; otherwise say
   "model path configured, not exercised".
5. After the hackathon: Phase 5 interrupt/resume, Phase 6 replay, Phase 8
   holdout eval, Phase 9 export/ops.

## Run and verify
- Backend: `cd apps/api && uv sync --frozen && uv run python -m unittest discover -s tests -v`
  (offline regardless of `.env`; `COVENANT_TEST_KEEP_ENV=1` keeps it).
- API: `uv run uvicorn main:app --port 8123`; worker: `uv run python -m src.platform.worker`.
- Web: `cd apps/web && npm ci && npm run build` (or `npm run dev`).
- Compose: `docker compose up --build` (litellm, api, worker, web).
