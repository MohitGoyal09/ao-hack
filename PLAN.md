# PLAN: Phase 5 — tools and durable human review

Tier: correctness-first agent slice. Subagents implement leaves under skill
discipline; reviewer fixes; parent wires tools into the graph, re-runs all
checks, commits.

## Goal (handoff Phase 5 done-criteria)

A real Gemini run calls tools, pauses, survives restart, resumes only with
the matching server-authorized decision, and matches deterministic
calculation. Model never does arithmetic or approvals.

## Skill discipline (all agents on this slice)

Every implementer MUST invoke these skills via the skill tool and follow them:
`test-driven-development` (failing test first, red-green), and
`verification-before-completion` (fresh command output before any done claim).
State the skill names in your final report with what each changed.

## Shared contracts (fixed before fan-out)

- Model access: ChatOpenAI pointed at the LiteLLM proxy
  (`LITELLM_BASE_URL`, api_key `LITELLM_API_KEY`, model alias
  `covenant-fast`/`covenant-strong`). temperature=0, parallel_tool_calls off
  (existing agent.py pattern). Credential-gated tests skip unless
  `LITELLM_API_KEY` is set; connection failure to the proxy is also a skip
  with a clear message (proxy runs via `docker compose up litellm`).
- Recording (`src/model_calls.py`, Leaf A): `ModelCallRecorder(dsn)`
  memory+Postgres; `record(*, organization_id, case_id, revision_id,
  alias, resolved_model, prompt_version, call_id, input_hash, latency_ms,
  retries, prompt_tokens, completion_tokens, cost_usd: str|None,
  status, error_class=None) -> str (row id)`. Cost numeric in Postgres,
  exact string on the wire. New table `model_call_records` via a NEW
  forward migration (Leaf A creates it with
  `supabase migration new model_call_records --workdir apps/api`).
  No raw prompts, documents, or reasoning stored — hashes and counts only.
- Proposal schemas (`src/model_calls.py`, Leaf A): pydantic
  `DefinitionProposal{term, meaning, clause_refs: list[str],
  confidence: Literal[high,medium,low]}`,
  `FactProposal{fact_key, amount: str (exact decimal), currency,
  period_start, period_end, evidence_refs: list[str]}`,
  `ReviewRequestPayload{revision_id, issue_kind, rationale,
  evidence_requirements: list[str], conditional_impact: dict}`.
  Strict validation (bad comparator/empty rationale/non-decimal amount
  rejected).
- Case tools (`src/case_tools.py`, Leaf B): plain functions returning JSON
  strings, never raising except programming errors (return {"error": ...}
  JSON): `open_case(case_id)`, `register_document(case_id, document_id)`,
  `inventory_covenants(case_id)`, `explain_results(case_id)`,
  `prepare_package(case_id)`. Read persisted state only (revision repo
  snapshot, document service metadata, demo workflow catalog for rule text).
  No filesystem paths, no DB writes, no invented figures.
- Review gate (`src/review_gate.py`, Leaf C): `ReviewGate(dsn)` memory+
  Postgres over the EXISTING `public.review_issues` table via its own SQL
  (columns: id, organization_id, case_id, revision_id, issue_kind, status,
  expected_bundle_hash, evidence_requirements jsonb, conditional_impact
  jsonb); `request_review(*, organization_id, case_id, revision_id,
  issue_kind, expected_bundle_hash, rationale, evidence_requirements,
  conditional_impact) -> {issue_id, external_issue_id}` (status open);
  `check_resume(external_issue_id, organization_id, decision,
  expected_bundle_hash) -> review_decision row | raises StaleCommandError`.
  `make_request_review_tool(gate, organization_id)` returns a langchain
  @tool function that calls `request_review` then langgraph `interrupt()`.
  `resume_after_review(graph, config, decision_payload)` wraps
  `graph.invoke(Command(resume=...), config)`.
- Live proof (Leaf D, `tests/test_gemini_proof.py` only): structured-output
  contract on `covenant-fast` (with_structured_output over one Leaf A
  schema), one tool-call round trip asserting valid args, usage recorded
  via Leaf A recorder (import allowed). Skip unless `LITELLM_API_KEY`;
  proxy unreachable -> skipTest (prerequisite missing, not a pass).
- Conventions: unittest only; parameterized SQL only; offline demo org
  "demo-org"; full suite green before finishing.

## Leaves and ownership (disjoint — no shared files)

- Leaf A: `supabase/migrations/*_model_call_records.sql` (new, via CLI),
  `src/model_calls.py` (new), `tests/test_model_calls.py` (new).
- Leaf B: `src/case_tools.py` (new), `tests/test_agent_tools.py` (new).
- Leaf C: `src/review_gate.py` (new), `tests/test_review_gate.py` (new).
- Leaf D: `tests/test_gemini_proof.py` (new). No source changes.
- Leaf E (after A–D): review full diff, fix all bugs, re-run both suites.
- Parent (me) after E: wire new tools into `build_agent_graph`, re-run
  everything, push migration to hosted, commit, push.

## Verification hierarchy

Leaf checks itself (target + full suite). Reviewer re-runs both suites plus a
live end-to-end where possible. Parent re-runs: full suite offline +
integration, web build, local lint, diff-check. Root GATES.md holds
whole-project gates.

## Status log

- 2026-09-06: plan written; leaves A–D dispatched in parallel.
