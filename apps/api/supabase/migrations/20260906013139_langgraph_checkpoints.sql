-- LangGraph PostgresSaver checkpoint tables, tracked as a migration.
--
-- Statements are langgraph.checkpoint.postgres.base.MIGRATIONS v0..v9 from
-- langgraph-checkpoint-postgres 3.1.2. The web process deliberately never
-- calls PostgresSaver.setup() (shared-schema DDL is an operator action), so
-- the schema lives here instead. The checkpoint_migrations rows mirror what
-- setup() records, which makes a later setup() call a no-op.
--
-- Deviations from the library text: indexes drop CONCURRENTLY (migrations run
-- inside one transaction and the tables are empty when created); v5 is
-- "SELECT 1" in the library and is omitted; row level security is enabled so
-- PostgREST roles cannot read checkpoints (the API reaches these tables only
-- through DATABASE_URL as the table owner).

-- v0
CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
);

-- v1
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- v2
CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

-- v3
CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

-- v4
ALTER TABLE checkpoint_blobs ALTER COLUMN blob DROP not null;

-- v6..v8 (without CONCURRENTLY)
CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON checkpoints(thread_id);

CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id);

CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id);

-- v9
ALTER TABLE checkpoint_writes ADD COLUMN IF NOT EXISTS task_path TEXT NOT NULL DEFAULT '';

-- Tenant hardening: no PostgREST access (no policies => deny for anon/authenticated).
alter table public.checkpoint_migrations enable row level security;

alter table public.checkpoints enable row level security;

alter table public.checkpoint_blobs enable row level security;

alter table public.checkpoint_writes enable row level security;

-- Bookkeeping identical to PostgresSaver.setup(): v0..v9 applied.
insert into checkpoint_migrations (v)
  select v from generate_series(0, 9) as v
  on conflict (v) do nothing;
