-- Revision persistence support: close domain/schema gaps without touching applied migrations.
--
-- Adds exact-money + rule binding on revisions, text-identifier change/impact
-- columns (domain doc/fact ids are text, not uuids), external review-issue ids
-- with resolution fields, approval bundle/superseded state, idempotent response
-- replay, case snapshots, and a generic idempotency ledger. All money stays
-- Postgres numeric; API boundaries serialize exact strings.

-- 1. Case revisions: exact threshold + rule binding.
alter table public.case_revisions
  add column if not exists threshold numeric,
  add column if not exists rule_id text;

create index if not exists case_revisions_rule_idx
  on public.case_revisions (case_id, revision_id, rule_id);

-- 2. Change sets: domain identifiers are text (e.g. amendment ids, fact keys).
alter table public.change_sets
  add column if not exists added_documents text[] not null default '{}',
  add column if not exists replaced_documents text[] not null default '{}',
  add column if not exists changed_fact_keys text[] not null default '{}',
  add column if not exists changed_decision_ids text[] not null default '{}';

-- 3. Impact sets: text-identifier complements to the uuid arrays.
alter table public.impact_sets
  add column if not exists affected_fact_keys text[] not null default '{}',
  add column if not exists dependent_calculations text[] not null default '{}',
  add column if not exists unaffected_references text[] not null default '{}',
  add column if not exists invalidated_decision_refs text[] not null default '{}',
  add column if not exists stale_artifact_refs text[] not null default '{}';

-- 4. Review issues: external text ids (e.g. case-rev-evidence-1) + resolution fields.
alter table public.review_issues
  add column if not exists external_issue_id text,
  add column if not exists resolved_by uuid references auth.users(id),
  add column if not exists decision_kind text,
  add column if not exists rationale text,
  add column if not exists evidence_refs jsonb not null default '[]'::jsonb;

create unique index if not exists review_issues_org_external_idx
  on public.review_issues (organization_id, external_issue_id)
  where external_issue_id is not null;
create index if not exists review_issues_case_revision_idx
  on public.review_issues (case_id, revision_id, status);

-- 5. Review decisions: store the original response for idempotent replay.
alter table public.review_decisions
  add column if not exists response jsonb;

-- 6. Approval bindings: bundle hash + superseded state.
alter table public.approval_bindings
  add column if not exists bundle_hash text,
  add column if not exists superseded boolean not null default false;

create index if not exists approval_bindings_case_superseded_idx
  on public.approval_bindings (case_id, revision_id, superseded, created_at desc);

-- 7. Case snapshots: one immutable snapshot per revision.
create table if not exists public.case_snapshots (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  case_id text not null,
  revision_id text not null,
  snapshot jsonb not null,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  primary key (case_id, revision_id),
  foreign key (organization_id, case_id, revision_id)
    references public.case_revisions (organization_id, case_id, revision_id)
    on delete cascade
);

create index if not exists case_snapshots_org_idx
  on public.case_snapshots (organization_id, case_id);

-- 8. Generic idempotency ledger (review resolution + approval replay).
create table if not exists public.revision_idempotency (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  idempotency_key text not null check (length(trim(idempotency_key)) between 1 and 200),
  request_hash text not null check (request_hash ~ '^[0-9a-f]{64}$'),
  response jsonb not null,
  created_at timestamptz not null default now(),
  primary key (organization_id, idempotency_key)
);

create index if not exists revision_idempotency_org_created_idx
  on public.revision_idempotency (organization_id, created_at desc);

-- 9. RLS + grants for new tables (mirror existing member-select pattern).
alter table public.case_snapshots enable row level security;
alter table public.revision_idempotency enable row level security;

drop policy if exists case_snapshots_select_member on public.case_snapshots;
create policy case_snapshots_select_member
  on public.case_snapshots for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = case_snapshots.organization_id
        and m.user_id = (select auth.uid())
    )
  );

drop policy if exists revision_idempotency_select_member on public.revision_idempotency;
create policy revision_idempotency_select_member
  on public.revision_idempotency for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = revision_idempotency.organization_id
        and m.user_id = (select auth.uid())
    )
  );

grant usage on schema public to authenticated;
grant select on public.case_snapshots, public.revision_idempotency to authenticated;
grant all on public.case_snapshots, public.revision_idempotency to service_role;
