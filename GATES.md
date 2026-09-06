# Gates — Covenant Certificate human-review fix + chat-first frontend

Mode: solo. Rule zero: done means every box checked with evidence, or an
ABANDON line with a reason. No report until the ledger is full.

## PHASE 0 — unsafe review/approval fix (P0, first)

- [ ] G0.1 Failing regression test reproduces the exact contradiction:
  accept issue → run still `waiting_review` + result `NEEDS_REVIEW` +
  package `ready_for_officer_review` → officer approval succeeds.
  CHECK: `cd apps/api && uv run python -m unittest tests.test_review_approval_safety -v`
  EXPECT: FAIL before fix (approval returns 200), PASS after fix (approval returns 409)
  EVIDENCE: RED observed 2026-09-06 (6 failures incl. optimistic
  `ready_for_officer_review` + approval 200 + request_document closing the
  issue); GREEN after fix (5/5 pass). Fix: resolve records + queues durable
  recalculation (CasePipeline recalc branch via job queue/worker, Decimal,
  stale artifact rotation, CALCULATION/RECALCULATION_COMPLETED +
  PACKAGE_REVISED events, ready only when completed + zero blockers);
  approve gated on completed run + ready package + current calc artifact
  (stored_at/created_at postdates latest decision) in both memory and
  Postgres paths, no DDL. Route no longer fabricates fixture numbers.
- [ ] G0.2 Officer approval rejected (409/422) when: run is `waiting_review`;
  current result stale or `NEEDS_REVIEW`; blocking issues remain;
  no current calculation artifact; package hash or revision stale.
  CHECK: same suite as G0.1
  EXPECT: all five rejections observed
  EVIDENCE: pending
- [ ] G0.3 `request_document` and unresolved decisions remain blocking
  (never resolve to ready/approved).
  CHECK: same suite as G0.1
  EXPECT: PASS
  EVIDENCE: pending
- [ ] G0.4 `accept_evidence` / `reject_evidence` / `correct_mapping`
  invalidate affected outputs; no optimistic `ready_for_officer_review`
  from the resolve response.
  CHECK: same suite as G0.1
  EXPECT: PASS
  EVIDENCE: pending
- [ ] G0.5 Review decision resumes the paused run or enqueues a durable
  recalculation for the same current revision; deterministic Decimal
  recompute persists calculation, coverage, draft, package hash, events;
  `ready_for_officer_review` only after current run completes with zero
  blockers and current hash.
  CHECK: same suite as G0.1
  EXPECT: PASS
  EVIDENCE: pending
- [ ] G0.6 Full backend suite green.
  CHECK: `cd apps/api && uv run python -m unittest discover -s tests`
  EXPECT: exit 0 (suite prints its own count)
  EVIDENCE: 2026-09-06 backend session: 164 tests OK, 13 skipped
  (opt-in Postgres integration), zero failures. New file
  tests/test_review_approval_safety.py (5 tests) plus updated
  test_main_api.py, test_revision_auth.py, test_revision_repository.py.
  Post-subagent re-measure: 171 OK, 13 skipped (delta is exactly the +7
  catalog-immutability tests). `git diff --check` clean. Eval harness
  `scripts/eval.py` exit 0.
- [ ] G0.7 Templates immutable: opening a prepared case creates a fresh
  derived working case (or reliable reset); demo/QA never mutates templates.
  CHECK: full suite + manual derived-case flow
  EXPECT: PASS
  EVIDENCE: subagent 2026-09-06: REJECT chosen — catalog ids read-only
  (mutations 409 with derive pointer), POST /api/cases is the reset;
  tests/test_catalog_immutability.py 7/7 (RED first: 200 != 409).
  NOTE: direct catalog-id demo beats (e.g. demo-script Meridian resolve)
  now 409 — demo must derive first.
- [ ] G0.8 Viewer role: privileged controls hidden/disabled with required-role
  explanation; backend 403 authoritative.
  CHECK: `npm run build` + browser QA
  EXPECT: PASS
  EVIDENCE: subagent 2026-09-06: canMutate/canApprove gates on composer,
  case rail, upload, review inbox, revision panel, approval (Conversation,
  Composer, CaseRail); build green. Browser QA NOT run — open.
- [ ] G0.9 Copy fix: "review or approve the internally approved draft",
  never "sign the final certificate".
  CHECK: `grep -ri "sign the final" apps/web/src || echo CLEAN`
  EXPECT: CLEAN
  EVIDENCE: re-measured 2026-09-06: CLEAN. Live-model phrasing unverified.
- [ ] G0.10 Next.js smooth-scroll warning removed; CopilotKit Inspector and
  dev-only chrome disabled in demo build; CopilotKit/Lit warnings
  investigated without unsafe upgrades.
  CHECK: `cd apps/web && npm run build`
  EXPECT: exit 0, no smooth-scroll warning
  EVIDENCE: re-measured 2026-09-06: build green (5 routes), no
  scroll-behavior/smooth in src, showDevConsole={false}. Console-warning
  QA NOT run against live app — open.

## Chat-first frontend (after PHASE 0 green)

- [ ] G1.1 App shell + case rail; desktop-only below-1024px gate.
  CHECK: `cd apps/web && npm run build`
  EXPECT: exit 0
  EVIDENCE: subagent 2026-09-06: WorkspaceShell + CaseRail + ContextRail +
  Composer + useCaseWorkspace (2s/10s snapshot+event-cursor polling);
  matchMedia(max-width:1023px) desktop gate; build green re-measured.
  Browser QA NOT run — open.
- [ ] G1.2 Central structured conversation + seven-stage workflow rail +
  Evidence/Artifacts tabs + inline domain cards + in-conversation review
  interrupt + revision diff + draft preview + officer approval.
  CHECK: browser QA at 1024px and 1440px
  EXPECT: PASS
  EVIDENCE: implemented (stages from snapshot+events only, stale on
  invalidation; focus-in/focus-return on interrupts; gated privileged
  controls) — browser QA NOT run, no web test harness — open.
- [ ] G1.3 Full flow verified: derived case → calculate → review interrupt →
  decision → durable recompute → revised package → approval → amendment →
  old approval invalidated. Frontend shows
  decision recorded → recalculating → controls checked → revised draft ready.
  CHECK: browser QA + backend suite
  EXPECT: PASS
  EVIDENCE: backend flow proven 2026-09-06 via API probe: derived case →
  accept → queued → early-approve 409 → worker recalc (completed, ready,
  ratio 3.14) → approve 200 locked → amendment rev-2 (draft, old
  SUPERSEDED) → old replay 409; events
  REVIEW_RESOLVED→RESULT_INVALIDATED→RUN_STARTED→CALCULATION_COMPLETED→
  RECALCULATION_COMPLETED→RUN_COMPLETED→PACKAGE_REVISED→APPROVAL_RECORDED→
  INPUT_CHANGED→RESULT_INVALIDATED. Frontend transition wired to
  snapshot+events polling; browser QA NOT run — open.
- [ ] G1.4 Diff reviewed (auth, stale-state, a11y, secrets); handoff updated
  with observed evidence and remaining gaps.
  CHECK: `git diff --check`
  EXPECT: exit 0
  EVIDENCE: diff --check clean; main.py guard ordering (401/403/404 before
  catalog 409) reviewed; no secrets in diff (no .env content); handoff gaps
  table updated 2026-09-06. No commit/push (not requested).

## Constraints (standing)

- No commit/push unless explicitly asked. No Supabase schema or shared-DB
  mutation without approval. No secrets printed. Current code wins over docs.
- Stop and report if durable review resumption needs a schema migration or
  shared Supabase mutation.
