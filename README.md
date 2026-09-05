# Covenant Certificate

**Track 2 — Autonomous Office of the CFO** entry for Syndicate by Maximor.

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

## Run locally

The project uses a Next.js UI and FastAPI service. Docker is the most reliable route because it includes Python and installs locked dependencies.

```bash
docker compose up --build
```

Open <http://localhost:3000>. The API health endpoint is <http://localhost:8123/health>.

No model key, database, or Supabase project is needed for the curated demonstration cases. The `.env.example` file documents environment values reserved for production persistence and document intake. The repository also includes an optional LiteLLM proxy configuration for controlled provider routing when an extraction-model integration is enabled.

## API

```text
GET  /health
GET  /api/demo-cases
GET  /api/cases/{case_id}
POST /api/cases/{case_id}/run
```

The last endpoint accepts an optional reviewer decision for the evidence-gap scenario:

```json
{ "reviewer_decision": "approve_addback", "reviewer_name": "Treasury reviewer" }
```

## AO usage during the hackathon

AO was used from the beginning to coordinate independent research and implementation work. The project was decomposed into parallel research tracks, including a primary-source covenant-controls review, while the main build integrated the product workflow. AO is a development tool only; the deployed Covenant Certificate workflow is standalone and does not depend on AO at runtime.

## Repository layout

```text
apps/web        Next.js control-room UI and server-side API proxy
apps/api        FastAPI API plus typed covenant calculator and review policy
data            curated SEC/PDF/XLSX demonstration corpus
docs            domain research, architecture, plans, and primary-source controls brief
infra           optional LiteLLM proxy configuration
references      read-only upstream integration/design references
```

## Production next steps

The hackathon demo uses curated in-memory cases to make the workflow inspectable. Before handling customer data, implement authenticated intake, private document storage, versioned rule/fact persistence, approved reviewer roles, immutable audit storage, and agreement-specific PDF rendering. The architecture plan in `docs/` details this hardening path.
