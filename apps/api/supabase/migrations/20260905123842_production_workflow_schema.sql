-- Production workflow records for Covenant Certificate.
--
-- Design rules:
-- * every customer-owned row has organization_id;
-- * raw document versions, case revisions, decisions, approvals, and events
--   are append-only for authenticated clients;
-- * service workers write through the backend with the secret key;
-- * financial values remain exact decimal text at API boundaries and numeric
--   in Postgres where calculations or comparisons are needed.

create extension if not exists pgcrypto with schema extensions;

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(trim(name)) between 1 and 160),
  slug text not null unique check (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);

create table public.organization_members (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('viewer', 'treasury_reviewer', 'officer', 'admin')),
  created_at timestamptz not null default now(),
  primary key (organization_id, user_id)
);

create index organization_members_user_idx
  on public.organization_members (user_id, organization_id);

create table public.covenant_cases (
  id text primary key,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null check (length(trim(name)) between 1 and 240),
  borrower_name text not null check (length(trim(borrower_name)) > 0),
  facility_name text not null check (length(trim(facility_name)) > 0),
  test_date date,
  state text not null default 'draft'
    check (state in ('draft', 'active', 'archived')),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id)
);

create index covenant_cases_org_updated_idx
  on public.covenant_cases (organization_id, updated_at desc);

create table public.documents (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  case_id text not null references public.covenant_cases(id) on delete cascade,
  document_role text not null
    check (document_role in (
      'credit_agreement', 'amendment', 'financial_statement',
      'supporting_evidence', 'certificate_form'
    )),
  title text not null check (length(trim(title)) > 0),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  unique (organization_id, id)
);

create index documents_case_role_idx
  on public.documents (case_id, document_role, created_at);
create index documents_org_case_idx
  on public.documents (organization_id, case_id);

create table public.document_versions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  document_id uuid not null references public.documents(id) on delete cascade,
  version_number integer not null check (version_number > 0),
  storage_bucket text not null default 'covenant-private',
  storage_path text not null,
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  byte_size bigint not null check (byte_size > 0 and byte_size <= 52428800),
  media_type text not null,
  source_url text,
  effective_date date,
  period_start date,
  period_end date,
  extraction_state text not null default 'pending'
    check (extraction_state in (
      'pending', 'extracting', 'extracted', 'needs_ocr',
      'unsupported', 'failed'
    )),
  uploaded_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  unique (document_id, version_number),
  unique (storage_bucket, storage_path),
  unique (organization_id, sha256)
);

create index document_versions_document_created_idx
  on public.document_versions (document_id, created_at desc);
create index document_versions_org_state_idx
  on public.document_versions (organization_id, extraction_state);

create table public.case_revisions (
  case_id text not null references public.covenant_cases(id) on delete cascade,
  revision_id text not null,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  parent_revision_id text,
  test_date date,
  input_bundle_hash text not null check (length(input_bundle_hash) >= 32),
  rulebook_hash text not null check (length(rulebook_hash) >= 32),
  mapping_hash text not null check (length(mapping_hash) >= 32),
  calculation_hash text,
  coverage_hash text,
  package_hash text,
  run_state text not null default 'queued'
    check (run_state in (
      'queued', 'running', 'waiting_review', 'completed', 'failed', 'cancelled'
    )),
  package_state text not null default 'draft'
    check (package_state in (
      'draft', 'ready_for_officer_review', 'approved_draft', 'superseded'
    )),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  primary key (case_id, revision_id),
  foreign key (case_id, parent_revision_id)
    references public.case_revisions(case_id, revision_id)
);

create unique index case_revisions_one_current_idx
  on public.case_revisions (case_id)
  where package_state <> 'superseded';
create index case_revisions_org_created_idx
  on public.case_revisions (organization_id, created_at desc);

create table public.revision_documents (
  case_id text not null,
  revision_id text not null,
  document_version_id uuid not null references public.document_versions(id),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  controlling boolean not null default false,
  primary key (case_id, revision_id, document_version_id),
  foreign key (case_id, revision_id)
    references public.case_revisions(case_id, revision_id) on delete cascade
);

create index revision_documents_version_idx
  on public.revision_documents (document_version_id);

create table public.change_sets (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  case_id text not null,
  source_revision_id text,
  target_revision_id text not null,
  event_reason text not null check (length(trim(event_reason)) > 0),
  change_kind text not null,
  changed_document_version_ids uuid[] not null default '{}',
  changed_fact_ids uuid[] not null default '{}',
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  foreign key (case_id, target_revision_id)
    references public.case_revisions(case_id, revision_id) on delete cascade,
  foreign key (case_id, source_revision_id)
    references public.case_revisions(case_id, revision_id)
);

create index change_sets_target_idx
  on public.change_sets (case_id, target_revision_id);

create table public.impact_sets (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  case_id text not null,
  revision_id text not null,
  changed_definition_ids text[] not null default '{}',
  affected_rule_ids text[] not null default '{}',
  affected_fact_ids uuid[] not null default '{}',
  stale_artifact_ids uuid[] not null default '{}',
  invalidated_decision_ids uuid[] not null default '{}',
  review_requirements jsonb not null default '[]'::jsonb,
  semantic_impact_uncertain boolean not null default false,
  created_at timestamptz not null default now(),
  unique (case_id, revision_id),
  foreign key (case_id, revision_id)
    references public.case_revisions(case_id, revision_id) on delete cascade
);

create table public.covenant_rules (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  case_id text not null,
  revision_id text not null,
  external_rule_id text not null,
  covenant_type text not null,
  support_state text not null
    check (support_state in ('supported', 'unsupported', 'not_applicable')),
  comparator text check (comparator in ('<=', '>=', '<', '>', '=')),
  threshold numeric,
  measurement_period text,
  structured_rule jsonb not null,
  source_spans jsonb not null default '[]'::jsonb,
  reviewed_by uuid references auth.users(id),
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (case_id, revision_id, external_rule_id),
  foreign key (case_id, revision_id)
    references public.case_revisions(case_id, revision_id) on delete cascade
);

create index covenant_rules_revision_idx
  on public.covenant_rules (case_id, revision_id);

create table public.financial_facts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  case_id text not null,
  revision_id text not null,
  fact_key text not null,
  amount numeric,
  currency text,
  unit_scale integer not null default 1 check (unit_scale > 0),
  period_start date,
  period_end date,
  evidence_state text not null
    check (evidence_state in ('proposed', 'accepted', 'rejected', 'missing')),
  source_spans jsonb not null default '[]'::jsonb,
  reviewed_by uuid references auth.users(id),
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (case_id, revision_id, fact_key),
  foreign key (case_id, revision_id)
    references public.case_revisions(case_id, revision_id) on delete cascade
);

create index financial_facts_revision_idx
  on public.financial_facts (case_id, revision_id);

create table public.review_issues (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  case_id text not null,
  revision_id text not null,
  issue_kind text not null,
  status text not null default 'open'
    check (status in ('open', 'resolved', 'superseded')),
  expected_bundle_hash text not null,
  evidence_requirements jsonb not null default '[]'::jsonb,
  conditional_impact jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  resolved_at timestamptz,
  foreign key (case_id, revision_id)
    references public.case_revisions(case_id, revision_id) on delete cascade
);

create index review_issues_open_idx
  on public.review_issues (organization_id, created_at)
  where status = 'open';

create table public.review_decisions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  issue_id uuid not null references public.review_issues(id),
  case_id text not null,
  revision_id text not null,
  actor_id uuid not null references auth.users(id),
  actor_role text not null
    check (actor_role in ('treasury_reviewer', 'officer', 'admin')),
  decision_kind text not null,
  rationale text not null check (length(trim(rationale)) > 0),
  evidence_refs jsonb not null default '[]'::jsonb,
  idempotency_key text not null,
  request_hash text not null,
  created_at timestamptz not null default now(),
  unique (organization_id, idempotency_key),
  foreign key (case_id, revision_id)
    references public.case_revisions(case_id, revision_id)
);

create index review_decisions_issue_idx
  on public.review_decisions (issue_id, created_at);

create table public.artifacts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  case_id text not null,
  revision_id text not null,
  artifact_type text not null
    check (artifact_type in (
      'calculation', 'coverage', 'evidence_manifest', 'audit_trace',
      'draft_package', 'draft_pdf'
    )),
  content_hash text not null,
  storage_bucket text,
  storage_path text,
  payload jsonb,
  state text not null default 'current'
    check (state in ('current', 'stale', 'superseded')),
  created_at timestamptz not null default now(),
  foreign key (case_id, revision_id)
    references public.case_revisions(case_id, revision_id) on delete cascade,
  check (
    (storage_path is not null and storage_bucket is not null)
    or payload is not null
  )
);

create index artifacts_revision_type_idx
  on public.artifacts (case_id, revision_id, artifact_type);

create table public.approval_bindings (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  case_id text not null,
  revision_id text not null,
  actor_id uuid not null references auth.users(id),
  actor_role text not null check (actor_role in ('officer', 'admin')),
  decision text not null check (decision in ('approved', 'rejected')),
  reason text not null check (length(trim(reason)) > 0),
  package_hash text not null,
  approved_ratio numeric,
  approved_threshold numeric,
  approved_comparator text check (approved_comparator in ('<=', '>=', '<', '>', '=')),
  approved_inputs jsonb not null default '{}'::jsonb,
  supersedes_approval_id uuid references public.approval_bindings(id),
  created_at timestamptz not null default now(),
  foreign key (case_id, revision_id)
    references public.case_revisions(case_id, revision_id)
);

create index approval_bindings_revision_idx
  on public.approval_bindings (case_id, revision_id, created_at desc);

create table public.domain_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  case_id text not null references public.covenant_cases(id) on delete cascade,
  revision_id text,
  run_id text,
  sequence bigint not null check (sequence > 0),
  event_type text not null,
  redacted_summary jsonb not null default '{}'::jsonb,
  artifact_ids uuid[] not null default '{}',
  created_at timestamptz not null default now(),
  unique (case_id, sequence),
  foreign key (case_id, revision_id)
    references public.case_revisions(case_id, revision_id)
);

create index domain_events_replay_idx
  on public.domain_events (case_id, sequence);
create index domain_events_run_idx
  on public.domain_events (run_id, sequence)
  where run_id is not null;

-- Connect the existing durable queue to tenant and revision records. Columns
-- remain nullable for a safe forward migration when old prototype rows exist.
alter table public.revision_run_jobs
  add column if not exists organization_id uuid
    references public.organizations(id) on delete cascade;

create index if not exists revision_run_jobs_org_state_idx
  on public.revision_run_jobs (organization_id, state, created_at);

-- Shared timestamp trigger. It is invoker-security and does not bypass RLS.
create or replace function public.covenant_set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end
$$;

create trigger covenant_cases_touch_updated_at
  before update on public.covenant_cases
  for each row execute function public.covenant_set_updated_at();

-- RLS is defense in depth even though normal writes go through the backend.
alter table public.organizations enable row level security;
alter table public.organization_members enable row level security;
alter table public.covenant_cases enable row level security;
alter table public.documents enable row level security;
alter table public.document_versions enable row level security;
alter table public.case_revisions enable row level security;
alter table public.revision_documents enable row level security;
alter table public.change_sets enable row level security;
alter table public.impact_sets enable row level security;
alter table public.covenant_rules enable row level security;
alter table public.financial_facts enable row level security;
alter table public.review_issues enable row level security;
alter table public.review_decisions enable row level security;
alter table public.artifacts enable row level security;
alter table public.approval_bindings enable row level security;
alter table public.domain_events enable row level security;

-- Membership rows: a user can read only their own memberships. Membership
-- management stays server-side because role changes are security-sensitive.
create policy organization_members_select_self
  on public.organization_members for select to authenticated
  using ((select auth.uid()) = user_id);

create policy organizations_select_member
  on public.organizations for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = organizations.id
        and m.user_id = (select auth.uid())
    )
  );

-- Member-readable records.
create policy covenant_cases_select_member
  on public.covenant_cases for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = covenant_cases.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy documents_select_member
  on public.documents for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = documents.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy document_versions_select_member
  on public.document_versions for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = document_versions.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy case_revisions_select_member
  on public.case_revisions for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = case_revisions.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy revision_documents_select_member
  on public.revision_documents for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = revision_documents.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy change_sets_select_member
  on public.change_sets for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = change_sets.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy impact_sets_select_member
  on public.impact_sets for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = impact_sets.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy covenant_rules_select_member
  on public.covenant_rules for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = covenant_rules.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy financial_facts_select_member
  on public.financial_facts for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = financial_facts.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy review_issues_select_member
  on public.review_issues for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = review_issues.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy review_decisions_select_member
  on public.review_decisions for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = review_decisions.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy artifacts_select_member
  on public.artifacts for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = artifacts.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy approval_bindings_select_member
  on public.approval_bindings for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = approval_bindings.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy domain_events_select_member
  on public.domain_events for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = domain_events.organization_id
        and m.user_id = (select auth.uid())
    )
  );

-- Authenticated clients can create only top-level case and upload metadata.
-- The backend verifies roles again and owns all derived-state writes.
create policy covenant_cases_insert_reviewer
  on public.covenant_cases for insert to authenticated
  with check (
    created_by = (select auth.uid())
    and exists (
      select 1 from public.organization_members m
      where m.organization_id = covenant_cases.organization_id
        and m.user_id = (select auth.uid())
        and m.role in ('treasury_reviewer', 'officer', 'admin')
    )
  );

create policy documents_insert_reviewer
  on public.documents for insert to authenticated
  with check (
    created_by = (select auth.uid())
    and exists (
      select 1 from public.organization_members m
      where m.organization_id = documents.organization_id
        and m.user_id = (select auth.uid())
        and m.role in ('treasury_reviewer', 'officer', 'admin')
    )
  );

create policy document_versions_insert_reviewer
  on public.document_versions for insert to authenticated
  with check (
    uploaded_by = (select auth.uid())
    and exists (
      select 1 from public.organization_members m
      where m.organization_id = document_versions.organization_id
        and m.user_id = (select auth.uid())
        and m.role in ('treasury_reviewer', 'officer', 'admin')
    )
  );

-- Organization-scoped private storage. The first path segment is organization ID.
create policy organization_members_read_covenant_objects
  on storage.objects for select to authenticated
  using (
    bucket_id = 'covenant-private'
    and exists (
      select 1 from public.organization_members m
      where m.organization_id::text = (storage.foldername(name))[1]
        and m.user_id = (select auth.uid())
    )
  );

create policy organization_reviewers_upload_covenant_objects
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'covenant-private'
    and exists (
      select 1 from public.organization_members m
      where m.organization_id::text = (storage.foldername(name))[1]
        and m.user_id = (select auth.uid())
        and m.role in ('treasury_reviewer', 'officer', 'admin')
    )
  );

-- The Data API uses explicit grants. RLS still determines visible rows.
revoke all on all tables in schema public from anon;
grant usage on schema public to authenticated;
grant select on public.organizations, public.organization_members,
  public.covenant_cases, public.documents, public.document_versions,
  public.case_revisions, public.revision_documents, public.change_sets,
  public.impact_sets, public.covenant_rules, public.financial_facts,
  public.review_issues, public.review_decisions, public.artifacts,
  public.approval_bindings, public.domain_events to authenticated;
grant insert on public.covenant_cases, public.documents,
  public.document_versions to authenticated;

-- Backend service role owns derived writes and queue operations.
grant all on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;
