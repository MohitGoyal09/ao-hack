# Covenant Certificate

**Track 2 - Autonomous Office of the CFO** entry for Syndicate by Maximor.

Start implementation with [the current implementation contract](docs/implementation-contract.md), then the [backend plan](docs/superpowers/plans/2026-09-04-covenant-certificate-backend.md). The product prepares covenant reporting, rechecks changed inputs, resolves evidence exceptions, and produces a revised draft for officer review. [Dataset readiness](data/case-readiness.json) records the remaining evidence gaps; the current corpus is not yet a complete gold certification package.

Covenant Certificate is an evidence-first treasury workflow for preparing an officer-reviewed *draft* loan-covenant compliance certificate. It turns contract-specific rules and financial evidence into a cited, deterministic result. It does not give legal advice and never represents an AI result as a signed certificate.

## What the demo proves

- Same company financials can produce opposite results under different agreements.
- An amendment can replace the original threshold for a particular test period.
- Missing support for an EBITDA adjustment returns `NEEDS_REVIEW`, not a compliant result.
- Every number, clause, calculation, and review decision is exposed in the evidence trail.

The included cases are illustrative product data, not legal documents or legal conclusions.

## Product workflow

```text
Resolve controlling agreement and amendment
  -> compile cited covenant rule
  -> map financial evidence
  -> calculate with typed deterministic code
  -> apply evidence/review policy
  -> prepare officer-reviewable draft and audit trace
```

The calculation code contains no `eval`, no model-generated code execution, and no LLM-issued verdict. A production extraction agent may propose structured facts and rules, but a human reviewer and the calculator remain the control boundary.

The Python backend is the product core. Its external interface is the `CovenantWorkflow`: callers select a case and submit an optional reviewer decision. Behind that small interface, separate internal modules own the typed domain model, agreement catalog, deterministic calculator, evidence policy, evidence manifest, chained audit hashes, run history, and draft-certificate rendering. A real LangGraph state machine executes the control flow. The Next.js application is intentionally a thin, demo-ready presentation layer over those backend results.

## Stack

- **Frontend:** Next.js, CopilotKit, and AG-UI
- **Backend:** Python, FastAPI, and LangGraph
- **Application data:** Supabase Postgres with row-level security
- **Documents and certificates:** private Supabase Storage bucket
- **Authentication:** Supabase Auth bearer tokens
- **Agent traces:** optional Neatlogs LangGraph callback integration

All infrastructure integrations are optional in local demo mode. When Supabase is configured, the API validates the caller, stores run metadata, and writes the evidence artifact to private storage. Neatlogs receives operational identifiers and outcomes, never raw agreements or financial statement data.

## Run locally

The project uses a Next.js UI and FastAPI service. Docker is the most reliable route because it includes Python and installs locked dependencies.

```bash
docker compose up --build
```

Open <http://localhost:3000>. The API health endpoint is <http://localhost:8123/health>.

No model key, database, or Supabase project is needed for the curated demonstration cases. Copy `.env.example` to `.env` when enabling the production integrations. Apply `apps/api/supabase/migrations/202609050001_covenant_certificate.sql` to provision the tables, row-level security policies, and private artifact bucket. The repository also includes an optional LiteLLM proxy configuration for controlled provider routing when a model-backed copilot is enabled; without a model key, the copilot uses its deterministic offline LangGraph path.

The hosted `ao-hack` Supabase project is linked and all repository migrations
are applied. Team environment rules and safe public values are in
[`docs/team-environment.md`](docs/team-environment.md), with separate frontend
and backend templates under `config/team/`. Server keys and database passwords
must stay in the team secret manager.

## API

```text
GET  /health
GET  /api/demo-cases
GET  /api/cases/{case_id}
POST /api/cases/{case_id}/run
GET  /api/cases/{case_id}/history
POST /ag-ui
```

The last endpoint accepts an optional reviewer decision for the evidence-gap scenario:

```json
{ "reviewer_decision": "approve_addback", "reviewer_name": "Treasury reviewer" }
```

## Verify

```bash
cd apps/api
uv sync --frozen
uv run python -m unittest discover -s tests -v

cd ../web
npm ci
npm run build
```

The backend suite covers the four verdict scenarios, amendment precedence, calculation integrity, reviewer controls, audit-chain stability, optional platform adapters, API authentication behavior, and the AG-UI route registration.

## AO usage during the hackathon

AO was used from the beginning to coordinate independent research and implementation work. The project was decomposed into parallel research tracks, including a primary-source covenant-controls review, while the main build integrated the product workflow. AO is a development tool only; the deployed Covenant Certificate workflow is standalone and does not depend on AO at runtime.

## Repository layout

```text
apps/web        Next.js control-room UI and server-side API proxy
apps/api        FastAPI, LangGraph, agent, platform adapters, and Python covenant core
apps/api/litellm  optional LiteLLM proxy configuration (Gemini)
apps/api/supabase Postgres, RLS, Auth, and private Storage migration
data            curated SEC/PDF/XLSX demonstration corpus
docs            domain research, architecture, plans, and primary-source controls brief
docs/status-report-generator.md  readable project status update generated by the script below
scripts         developer utility scripts, incl. create_status_report.py (Word status report)
references      read-only upstream integration/design references
```

## Production next steps

The repository now includes authenticated Supabase persistence and private storage adapters, but the default demonstration data remains curated and in memory so every outcome is repeatable. Before handling real customer data, add an agreement-specific extraction pipeline, approved reviewer-role claims, immutable external audit retention, and final signed-PDF rendering. The architecture plan in `docs/` details this hardening path.
