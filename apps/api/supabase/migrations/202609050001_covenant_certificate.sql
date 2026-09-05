-- Covenant Certificate application data and private artifact controls.

create table if not exists public.covenant_runs (
  id text primary key,
  owner_id uuid not null references auth.users(id) on delete cascade,
  case_id text not null,
  status text not null check (status in ('DRAFT_COMPLIANT', 'DRAFT_BREACH', 'NEEDS_REVIEW')),
  result jsonb not null,
  certificate_id text not null,
  artifact_path text not null unique,
  created_at timestamptz not null default now()
);

create index if not exists covenant_runs_owner_created_idx
  on public.covenant_runs(owner_id, created_at desc);
create index if not exists covenant_runs_case_idx
  on public.covenant_runs(case_id, created_at desc);

create table if not exists public.approved_interpretations (
  id bigint generated always as identity primary key,
  owner_id uuid not null references auth.users(id) on delete cascade,
  agreement_id text not null,
  rule_id text not null,
  decision text not null check (decision in ('approve_addback', 'reject_addback')),
  rationale text not null check (length(trim(rationale)) > 0),
  evidence_object_path text,
  supersedes_id bigint references public.approved_interpretations(id),
  created_at timestamptz not null default now(),
  unique(owner_id, agreement_id, rule_id, created_at)
);

alter table public.covenant_runs enable row level security;
alter table public.approved_interpretations enable row level security;

create policy "owners read covenant runs"
  on public.covenant_runs for select
  using (auth.uid() = owner_id);

create policy "owners insert covenant runs"
  on public.covenant_runs for insert
  with check (auth.uid() = owner_id);

create policy "owners read interpretations"
  on public.approved_interpretations for select
  using (auth.uid() = owner_id);

create policy "owners insert interpretations"
  on public.approved_interpretations for insert
  with check (auth.uid() = owner_id);

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'covenant-private',
  'covenant-private',
  false,
  52428800,
  array['application/pdf', 'application/json', 'text/csv',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
)
on conflict (id) do update set
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create policy "users read own covenant artifacts"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'covenant-private'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "users upload own covenant artifacts"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'covenant-private'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
