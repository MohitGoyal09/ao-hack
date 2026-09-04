# Covenant Certificate

Track 2 project for Syndicate by Maximor.

## Repository layout

```text
apps/web        Next.js, CopilotKit, AG-UI frontend
apps/api        FastAPI and LangGraph backend
docs            Domain research and backend architecture
references      Read-only upstream design and integration references
```

## Runtime services

- Web: Next.js
- API: FastAPI plus LangGraph
- Database: Supabase Postgres in all environments
- Files: private Supabase Storage buckets
- Agent transport: AG-UI through CopilotKit
- Planned agent observability: Neatlogs

## Local development

Create or select a Supabase project, copy `.env.example` to `.env`, and provide its connection and API values. Dependencies have not been installed yet.

```bash
docker compose up --build
```

The expected application endpoints are:

- Web: http://localhost:3000
- API health: http://localhost:8123/health

## Deployment targets

- `apps/web`: Vercel or any Node.js container host
- `apps/api`: Railway, Render, Fly.io, or any container host
- Database, private files, and later authentication: Supabase
- Agent traces, evaluations, and debugging: Neatlogs

The web application communicates with the API through the server-side CopilotKit route. Database credentials and secret keys must never be exposed through `NEXT_PUBLIC_` variables.

The copied starter still uses in-memory agent state and demo data. The first backend implementation must replace those paths with Supabase Postgres persistence, private Supabase Storage, and verified Supabase Auth. Do not expose the raw agent endpoint publicly or enable CopilotKit Intelligence with its sample `demo-user` identity.

Neatlogs instrumentation is planned but not installed. Supabase will remain the authoritative audit store; Neatlogs will hold operational traces only.
