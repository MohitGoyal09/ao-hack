-- Durable revision-run job queue with leases, attempts, and fencing tokens.

create table if not exists public.revision_run_jobs (
  id text primary key,
  case_id text not null,
  revision_id text not null,
  state text not null default 'queued'
    check (state in ('queued', 'running', 'waiting_review', 'completed', 'failed', 'cancelled')),
  lease_owner text,
  lease_expires_at timestamptz,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 5 check (max_attempts >= 1),
  fencing_token bigint not null default 0,
  payload jsonb not null default '{}'::jsonb,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists revision_run_jobs_one_active_per_revision
  on public.revision_run_jobs (case_id, revision_id)
  where (state in ('queued', 'running', 'waiting_review'));

create index if not exists revision_run_jobs_claim_idx
  on public.revision_run_jobs (state, lease_expires_at)
  where (state in ('queued', 'running'));

create or replace function public.revision_run_jobs_touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists revision_run_jobs_touch on public.revision_run_jobs;
create trigger revision_run_jobs_touch
  before update on public.revision_run_jobs
  for each row execute function public.revision_run_jobs_touch_updated_at();

alter table public.revision_run_jobs enable row level security;

drop policy if exists "service role manages revision run jobs" on public.revision_run_jobs;
create policy "service role manages revision run jobs"
  on public.revision_run_jobs for all to service_role
  using (true) with check (true);
