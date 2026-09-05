# Hosted setup (Supabase project `ao-hack`)

Reproduce the hosted demo from a fresh checkout. Every command below is additive
and safe to re-run against the shared project. Never `db reset`, `db push`
without team approval, TRUNCATE/DELETE, or ad-hoc DDL there.

## 1. Prerequisites

- `uv` (Python 3.12+), Node 20 (`apps/web`), optionally the Supabase CLI.
- The two server-only values from the team secret store: `SUPABASE_SECRET_KEY`
  (`sb_secret_...`) and `DATABASE_URL` (Supavisor session pooler, port 5432,
  `sslmode=require`). The URL and publishable key are public (`docs/team-environment.md`).

## 2. Root `.env` (names only, values never in git)

`cp config/team/backend.env.example .env`, then fill:

| Key | Purpose |
|---|---|
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | project URL + browser-safe key (public) |
| `SUPABASE_SECRET_KEY`, `DATABASE_URL` | server-only; puts `main:app` and the worker in Postgres mode |
| `SUPABASE_STORAGE_BUCKET` | `covenant-private` |
| `DEMO_ORG_ID` | org slug, default `demo-treasury` (an existing org UUID also works) |
| `DEMO_OFFICER_EMAIL`, `DEMO_OFFICER_PASSWORD` | officer identity the seed creates; choose any email + strong password |
| `DEMO_REVIEWER_EMAIL`, `DEMO_REVIEWER_PASSWORD` | optional `treasury_reviewer` identity (shows the 403-for-non-officer beat) |
| `LITELLM_API_KEY`, `LITELLM_BASE_URL`, `LITELLM_STRONG_ALIAS` | optional live copilot model; blank key = deterministic offline chat graph |

`main.py` and `python -m src.platform.worker` auto-load this file. Force
offline mode with `DATABASE_URL= SUPABASE_URL= SUPABASE_SECRET_KEY= uv run ...`.

## 3. Migrations

```bash
supabase link --project-ref hbgnqhnwudazsyzfevox --workdir apps/api
supabase migration list --linked --workdir apps/api
```

Expect all 7 files in `apps/api/supabase/migrations/` to show as applied
(`202609050001` ... `20260906013139_langgraph_checkpoints`,
`20260906022716_case_template`). Without the CLI, the seed's `--check` below
prints `migrations applied=7 tracked=7`. If any are
missing: `supabase db push --linked --dry-run --workdir apps/api`, then push
with team approval.

## 4. Seed the demo identity

```bash
cd apps/api && uv run python ../../scripts/seed_demo_identity.py          # create-if-missing, then verify
cd apps/api && uv run python ../../scripts/seed_demo_identity.py --check  # read-only verification
```

Creates (only when absent) the Auth users via the admin API with
`email_confirm: true` and `app_metadata.role`, the `organizations` row for
`DEMO_ORG_ID`, and one `organization_members` row per user (`officer` /
`treasury_reviewer`; the role is the only thing ever updated). Prints
`created` vs `found` per item, then the check: user exists, membership role,
migration count, and a real password-grant login per identity (booleans and ids
only). Exit code 1 when a check fails or an env key is missing.

## 5. Run the API and the worker

```bash
cd apps/api && uv run uvicorn main:app --port 8123          # terminal 1: API, Postgres mode
cd apps/api && uv run python -m src.platform.worker        # terminal 2: leases jobs, runs the pipeline
docker compose up --build                                  # or: litellm + api + worker + web
```

`GET /health/ready` must return 200 with `durability.mode = "postgres"`.
Uploads create a revision plus a queued job; only the worker (compose service
`worker`, same command and env as above) moves a job to `completed` and writes
the calculation/evidence artifacts the snapshot shows.

## 6. Smoke test

```bash
cd apps/api && uv run python ../../scripts/hosted_smoke.py                          # read-only, :8123
cd apps/api && uv run python ../../scripts/hosted_smoke.py --api http://localhost:8131 --full
```

Read-only: officer login, `/health/ready`, `GET /api/cases/aurora-net-leverage/snapshot`
(`run_state`, `package_state`, artifact/review-issue/approval counts) and, when
`DEMO_REVIEWER_*` is set, reviewer snapshot 200 + officer-approval 403.
`--full` also uploads `data/raw/pdf-fixtures/aon-credit-agreement.pdf`, runs the
real `Worker.run_once` in-process with the real Supabase storage adapter (no
separate worker needed; if one is running it may lease the job first and the
script polls it), and re-reads the snapshot: expect `run_state=completed`,
`artifacts=5`. Every `--full` run adds one revision to the case (additive only).

## 7. Sign-in in the UI

`apps/web/.env.local`: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
(public values from `config/team/frontend.env.example`) and `AGENT_URL=http://localhost:8123`.
`cd apps/web && npm ci && npm run dev`, open `/` or `/cases/aurora-net-leverage`,
sign in with the seeded email + password. The browser then sends the Supabase
JWT as `Authorization: Bearer` through the same-origin proxy.

Authorization is the `organization_members.role` row, not the JWT claim
(`app_metadata.role` only labels the sign-in card and drives offline mode):

| Role | Snapshot / jobs | Upload, resolve review issue | Officer approval |
|---|---|---|---|
| `officer` (demo officer) | yes | yes | yes |
| `treasury_reviewer` (demo reviewer) | yes | yes | 403 `Officer role is required` |
| `viewer` | yes | 403 | 403 |
| not a member of the case org | 404 on every case | 404 | 404 |

The first snapshot read by a member seeds the case under that member's first
organization.

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `/health/ready` 503, `checkpoint` component unready; every other route 503 | LangGraph checkpoint tables missing: apply `20260906013139_langgraph_checkpoints.sql` (step 3). |
| 401 `The Supabase session is invalid` | The token was issued by a different project than the API's `SUPABASE_URL`/`SUPABASE_SECRET_KEY`, or it expired (1 h). Check both sides use the `ao-hack` keys; sign in again. |
| 401 `Authentication is required` | No bearer sent. In the UI sign in; with curl pass `Authorization: Bearer <access_token>`. |
| 404 `Unknown covenant case` for a real case id | The user is not in `organization_members` for the case's org (or has zero memberships). Re-run the seed with that user's `DEMO_*` env. |
| 403 on upload / resolve / approval | Membership role too low (see table above). |
| `POST /api/cases` fails with an unknown column `template_case_id` | `20260906022716_case_template.sql` not applied (step 3). |
| Upload stays `queued` | No worker running in Postgres mode (`INPROCESS_WORKER` is ignored there). Start step 5's worker or use `hosted_smoke.py --full`. |
| Seed exits `missing env` | Fill the listed keys in the root `.env`; `DEMO_REVIEWER_EMAIL` needs `DEMO_REVIEWER_PASSWORD`. |
