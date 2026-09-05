# Team environment setup

The hosted Supabase project is `ao-hack` in `ap-south-1`.

## Safe values

These values are public by design and are also committed in `.env.example`:

```dotenv
SUPABASE_PROJECT_REF=hbgnqhnwudazsyzfevox
SUPABASE_URL=https://hbgnqhnwudazsyzfevox.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_2LHgN7M2aDVBg0TAbwloTw_bgkAvp0i
NEXT_PUBLIC_SUPABASE_URL=https://hbgnqhnwudazsyzfevox.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_2LHgN7M2aDVBg0TAbwloTw_bgkAvp0i
```

The publishable key can be used in the browser. Row-level security still
controls which rows an authenticated user can access.

## Server-only secrets

Share these through 1Password, Bitwarden, Doppler, or another approved team
secret store. Never commit them and never paste them into chat:

```dotenv
SUPABASE_SECRET_KEY=
DATABASE_URL=
MIGRATION_DATABASE_URL=
GEMINI_API_KEY=
LITELLM_MASTER_KEY=
LITELLM_API_KEY=
NEATLOGS_API_KEY=
CPK_INTELLIGENCE_API_KEY=
```

- `SUPABASE_SECRET_KEY`: use the modern `sb_secret_...` project key. Backend only.
- `DATABASE_URL`: the current API/worker keeps connections open, so use the
  Supavisor session pooler on port 5432 when the host lacks IPv6. A serverless
  deployment should use transaction mode on port 6543 instead.
- `MIGRATION_DATABASE_URL`: use the direct connection on port 5432 for
  migrations. Direct hosted connections need IPv6 unless the project has the
  IPv4 add-on. Always add `sslmode=require`.
- Never use a secret/service key in `NEXT_PUBLIC_*` variables.
- Do not use JWT `user_metadata` for roles. Roles belong in app metadata and
  are enforced again by database membership records.

## Local setup

```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
supabase start --workdir apps/api
docker compose up --build
```

Fill server-only values in the root `.env`. The web file needs only the public
Supabase values and the API URL.

Ready-to-copy role templates are in `config/team/frontend.env.example` and
`config/team/backend.env.example`.

## Link and migration commands

```bash
supabase login
supabase link --project-ref hbgnqhnwudazsyzfevox --workdir apps/api
supabase migration list --linked --workdir apps/api
supabase db push --linked --dry-run --workdir apps/api
```

Applying a migration to the shared project requires team approval. Create new
migrations with the CLI:

```bash
supabase migration new descriptive_name --workdir apps/api
```

Never edit a migration that has already reached the hosted database.

## Current database proof

Update 2026-09-06 (hosted audit): 5 of 5 tracked migrations applied, 21 public
tables, private bucket confirmed, email/password Auth on, and the full
upload -> job -> worker -> snapshot -> review -> officer-approval path ran on
the hosted project. A sixth migration (`20260906013139_langgraph_checkpoints`)
adds the LangGraph checkpoint tables that readiness requires; it was applied to
the hosted project on 2026-09-06 (`supabase migration list --linked` 6/6,
`GET /health/ready` 200 with checkpoint mode `postgres`).

On 2026-09-05:

- all four repository migrations matched hosted migration history;
- local and hosted `supabase db lint` returned no schema errors;
- local reset created 17 workflow tables with RLS enabled on all 17;
- 24 public/storage policies existed;
- the `covenant-private` bucket was private with a 50 MiB limit;
- a rolled-back RLS test let a member see one tenant/case and an outsider see zero.

This proves schema installation and basic RLS behavior. It does not yet prove
backend persistence, hosted RLS with real users, worker recovery, or browser
authentication. Those remain implementation work in `docs/agent-handoff.md`.
