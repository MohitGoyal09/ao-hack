# Status report generator (create_status_report.py)

This page documents the `scripts/create_status_report.py` script and the project
status update it captures. The script renders a styled Word (`.docx`) status
report for the Covenant Certificate hackathon build, current as of
**5 September 2026**.

## Source script

- **File:** `scripts/create_status_report.py`
- **Purpose:** Generates a one-page Word report summarizing verified status,
  implemented work, test coverage, completion estimates, remaining work,
  immediate priorities, and current constraints.
- **Output:** `Covenant_Certificate_Project_Status_Report.docx`
- **Requirement:** `python-docx`
- **Run:** `py scripts/create_status_report.py` (or activate the backend
  environment in `apps/api` and run it from the repository root).

## What the script does

The script uses `python-docx` to build the report programmatically. It is split
into two parts:

1. **Reusable table helpers** — so every table in the document has the same
   navy header row, pale zebra striping, hairline borders, and center-aligned
   cells.
2. **Document assembly** — defines the page setup, fonts, styles, and then
   fills in every section of the report.

### Reusable helpers

| Helper | What it does |
|---|---|
| `set_cell_fill(cell, color)` | Fills a table cell with a hex color (navy header, pale blue / white body alternation). |
| `set_cell_borders(cell)` | Adds thin single-cell borders in `D9D9D9` around every side of a cell. |
| `set_cell_margins(cell, ...)` | Sets even inter-cell spacing (top / start / bottom / end margins in dxa units). |
| `format_table(table, widths)` | Centers the table, fixes cell widths in inches, applies header styling (navy fill, bold white 9 pt text) and body styling (9 pt text, dark gray color, zebra striping), and centers vertically. |
| `add_table(doc, headers, rows, widths)` | Creates a table from header/row lists, then calls `format_table`. |
| `add_bullets(doc, items)` | Adds a `List Bullet` paragraph per item with tight spacing. |

### Document design
- **Page area:** A4 with tightened margins (top 0.70 in, bottom 0.65 in, sides
  0.75 in) so the full report fits on one page.
- **Fonts:** `Aptos` for body text, `Aptos Display` for headings; title at
  25 pt, headings at 16 pt / 12 pt.
- **Body text:** 10 pt, color `RGB(31, 41, 55)` (`#1F2937`), line spacing 1.08.
- **Accent colors:** navy `#17365D` header rows, pale blue `#EAF1F8` zebra
  rows, pale gray `#F3F4F6`, border `#D9D9D9`.
- **Footer:** centered `"Covenant Certificate Project Status  |  5 September 2026"`
  in 8 pt gray.
- **Metadata:** document title, subject, and author are set on core properties.

## Report content — current project update

Below is the exact content the script writes, rendered readably.

### Current conclusion

The project has a working, tested hackathon prototype and the first production
durability controls. The overall prototype is approximately **50 percent**
complete. Production readiness is approximately **35 to 40 percent** because
the live persistence, upload, worker, durable review, event replay, and Gemini
paths are not yet complete end to end.

### Verified status

| Area | Verified result | Status |
|---|---|---|
| Repository | main at `cbe2599` and synchronized with `origin/main` | Passed |
| Backend dependencies | `uv sync --frozen` completed | Passed |
| Backend suite | 47 tests executed: 46 passed and 1 skipped | Passed with one live-test gap |
| Frontend dependencies | `npm ci` completed | Passed |
| Frontend production build | Next.js production build completed | Passed |
| Real Postgres restart test | Test exists but `TEST_DATABASE_URL` was unavailable | Not yet verified |
| Supabase linked migration and lint checks | CLI project link was unavailable on this machine | Not rerun |
| Real Gemini through LiteLLM | No configured Gemini key was available | Not tested |

### Implemented work

**Covenant calculation and controls**
- Python FastAPI backend and LangGraph orchestration are in place.
- Deterministic Python performs covenant arithmetic with evidence checks; the
  model does not decide the final calculation.
- Missing inputs, unclear document precedence, unsupported adjustments, and
  incomplete review evidence fail closed instead of becoming zero or a pass.
- The workflow can return a reviewed draft pass, draft breach, or needs-review
  result without claiming full agreement compliance.
- Agreement-specific thresholds, amendments, citations, calculation lines,
  certificate draft data, and a hash-based audit trace are represented.

**Extraction and review workflow**
- A narrow Aon agreement PDF and financial extraction flow works for the
  curated fixture.
- Case revisions, change impacts, stale-command conflicts, review resolutions,
  snapshots, and officer approval logic exist in memory.
- Officer approval is bound to the exact revision, package hash, threshold,
  ratio, comparator, and financial inputs.
- A later revision invalidates the previous approval instead of silently
  reusing it.

**Supabase and durability foundation**
- Four forward migrations define organizations, memberships, cases, immutable
  documents, revisions, impacts, rules, facts, reviews, approvals, artifacts,
  events, a job queue, row-level security, and private Storage policies.
- The queue implementation includes leases, retry counts, heartbeat handling,
  cancellation, and stale-worker fencing tokens.
- Postgres and LangGraph checkpoint dependencies are pinned in the Python
  lockfile.
- Configured queue or checkpoint failures no longer silently fall back to
  memory.
- Liveness and dependency-aware readiness endpoints report queue and checkpoint
  status separately and redact connection details.
- LangGraph checkpoint schema setup was removed from application startup and
  remains an explicit operator action.

**Frontend and agent interface**
- The Next.js interface presents cases, formulas, financial evidence, cited
  clauses, results, blockers, reviewer actions, and workflow trace data.
- CopilotKit and AG-UI connect the frontend to the LangGraph agent endpoint.
- The Turbopack workspace root is fixed to the web application, making the
  local production build deterministic.
- Unused starter travel, todo, and chart examples were removed so the
  repository reflects the covenant product.

### Test report

| Test area | Coverage | Result |
|---|---|---|
| Covenant core | Opposite agreement outcomes, amendments, evidence gaps, unsupported covenants, safe empty scope, audit hashes | Passed |
| Review and approval | Reviewer identity and rationale, stale decisions, idempotency, exact approval values, supersession | Passed |
| API and AG UI | HTTP workflow, missing cases, health, AG-UI route registration | Passed |
| Platform adapters | Offline mode, authentication requirement, safe observability behavior | Passed |
| Durability readiness | Explicit offline mode, redacted failure, liveness, blocked business traffic | Passed |
| Postgres durability | Queue and checkpoint reconstruction test | Skipped pending isolated database |
| Frontend | Clean install, TypeScript, optimized Next.js build and routes | Passed |

### Completion estimate

| Workstream | Estimated completion | Assessment |
|---|---|---|
| Deterministic covenant core | 85 percent | Working and well covered for curated leverage cases |
| Database schema and security foundation | 80 percent | Schema and policies exist; full runtime use remains |
| Durability and readiness foundation | 70 percent | Fail-closed behavior works; live restart proof remains |
| Revision, review, and approval | 55 percent | Strong in-memory behavior; Postgres repository replacement remains |
| Document intake and Storage | 30 percent | Narrow parser exists; authenticated immutable upload is missing |
| Production worker | 30 percent | Queue mechanics exist; worker execution is not connected end to end |
| Durable human interrupt and resume | 20 percent | Review logic exists, but paused graph recovery is missing |
| Durable AG UI events and replay | 20 percent | Basic transport exists; outbox, sequence, snapshot replay remain |
| Complete production frontend | 35 percent | Demo dashboard works; upload-through-approval flow remains |
| Gemini integration and accuracy evaluation | 15 percent | Aliases and labels exist; live calls and full harness remain |

**Overall engineering estimate:** approximately **50 percent** of the hackathon
prototype is implemented. Around **50 percent** remains for a complete
demonstration workflow. For production readiness, approximately **60 to
65 percent** remains because live infrastructure and recovery behavior carry
more risk than the existing interface and deterministic calculation code.

### Remaining work

1. Replace the global in-memory revision store with organization-scoped
   Supabase Postgres repositories.
2. Authenticate every private read and mutation and derive actor, organization,
   and role from verified server identity.
3. Implement authenticated multipart upload, content validation, SHA-256
   streaming, immutable private Storage, document versions, revisions, events,
   and queued jobs in one controlled flow.
4. Run a real worker that leases jobs, heartbeats, retries transient failures,
   recovers after restart, and prevents stale workers from publishing.
5. Persist extracted rules and facts as authoritative revision state and
   recalculate only after deterministic validation.
6. Add durable LangGraph interrupt and resume for matching human review
   decisions.
7. Persist redacted domain events and add ordered AG-UI snapshot and replay
   after browser reconnect.
8. Complete the frontend from Supabase sign-in and case creation through
   upload, review, recalculation, and exact officer approval.
9. Run authenticated Gemini calls through LiteLLM and verify tool use,
   structured output, retries, provider reporting, latency, tokens, and cost.
10. Complete the accuracy harness, holdout agreement family, citation checks,
    false-pass gates, security checks, PDF workpaper export, staging
    deployment, and restart runbook.

### Immediate priorities

| Priority | Next deliverable | Acceptance evidence |
|---|---|---|
| 1 | Postgres revision repositories and verified identity | Restart persistence, tenant isolation, role enforcement, stale 409 behavior |
| 2 | Immutable upload and worker connection | One upload creates object, version, revision, event, job, and recoverable result |
| 3 | Durable review and event replay | Paused run survives restart; reconnect replays each event once in order |
| 4 | Complete frontend workflow | Reviewer completes upload through current-revision approval on desktop and mobile |
| 5 | Gemini and evaluation proof | Real LiteLLM call tests plus versioned accuracy metrics and zero observed unsupported passes |

### Current constraints

**Live verification remains limited.** The latest local run did not have an
isolated Postgres test database, a linked Supabase CLI session, or a configured
Gemini key. The existing active tests and frontend build are green, but the
report does not claim that live database restart recovery, hosted row-level
security, Storage isolation, or real model calls have passed. Server credentials
must remain in ignored environment files or a secret manager and must never be
committed.

## Keeping this page up to date

When the implementation advances, update the tables and lists in
`scripts/create_status_report.py` (verified status, implemented work, test
results, completion percentages, remaining work, priorities) and re-run the
script to regenerate the `.docx`. Update this page in the same pass so the
readable view stays in sync with the generated Word report.