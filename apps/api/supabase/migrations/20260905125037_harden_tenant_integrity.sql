-- Security hardening after review of the production workflow schema.

-- Permissive policies are ORed. Remove the old user-folder policies so all new
-- document access follows the organization membership boundary.
drop policy if exists "users read own covenant artifacts" on storage.objects;
drop policy if exists "users upload own covenant artifacts" on storage.objects;

-- The same source file can validly appear in more than one case. Blob
-- deduplication belongs in a separate content-addressed blob model.
alter table public.document_versions
  drop constraint if exists document_versions_organization_id_sha256_key;

-- Composite uniqueness enables tenant-scoped foreign keys.
alter table public.documents
  add constraint documents_org_id_id_key unique (organization_id, id);
alter table public.document_versions
  add constraint document_versions_org_id_id_key unique (organization_id, id);
alter table public.case_revisions
  add constraint case_revisions_org_case_revision_key
    unique (organization_id, case_id, revision_id);
alter table public.review_issues
  add constraint review_issues_org_id_id_key unique (organization_id, id);
alter table public.approval_bindings
  add constraint approval_bindings_org_case_id_key
    unique (organization_id, case_id, id);

-- A denormalized organization ID must match every referenced parent.
alter table public.documents
  add constraint documents_org_case_fk
  foreign key (organization_id, case_id)
  references public.covenant_cases (organization_id, id);

alter table public.document_versions
  add constraint document_versions_org_document_fk
  foreign key (organization_id, document_id)
  references public.documents (organization_id, id);

alter table public.case_revisions
  add constraint case_revisions_org_case_fk
  foreign key (organization_id, case_id)
  references public.covenant_cases (organization_id, id),
  add constraint case_revisions_org_parent_fk
  foreign key (organization_id, case_id, parent_revision_id)
  references public.case_revisions (organization_id, case_id, revision_id);

alter table public.revision_documents
  add constraint revision_documents_org_revision_fk
  foreign key (organization_id, case_id, revision_id)
  references public.case_revisions (organization_id, case_id, revision_id)
  on delete cascade,
  add constraint revision_documents_org_document_version_fk
  foreign key (organization_id, document_version_id)
  references public.document_versions (organization_id, id);

alter table public.change_sets
  add constraint change_sets_org_target_fk
  foreign key (organization_id, case_id, target_revision_id)
  references public.case_revisions (organization_id, case_id, revision_id)
  on delete cascade,
  add constraint change_sets_org_source_fk
  foreign key (organization_id, case_id, source_revision_id)
  references public.case_revisions (organization_id, case_id, revision_id);

alter table public.impact_sets
  add constraint impact_sets_org_revision_fk
  foreign key (organization_id, case_id, revision_id)
  references public.case_revisions (organization_id, case_id, revision_id)
  on delete cascade;

alter table public.covenant_rules
  add constraint covenant_rules_org_revision_fk
  foreign key (organization_id, case_id, revision_id)
  references public.case_revisions (organization_id, case_id, revision_id)
  on delete cascade;

alter table public.financial_facts
  add constraint financial_facts_org_revision_fk
  foreign key (organization_id, case_id, revision_id)
  references public.case_revisions (organization_id, case_id, revision_id)
  on delete cascade;

alter table public.review_issues
  add constraint review_issues_org_revision_fk
  foreign key (organization_id, case_id, revision_id)
  references public.case_revisions (organization_id, case_id, revision_id)
  on delete cascade;

alter table public.review_decisions
  add constraint review_decisions_org_issue_fk
  foreign key (organization_id, issue_id)
  references public.review_issues (organization_id, id),
  add constraint review_decisions_org_revision_fk
  foreign key (organization_id, case_id, revision_id)
  references public.case_revisions (organization_id, case_id, revision_id);

alter table public.artifacts
  add constraint artifacts_org_revision_fk
  foreign key (organization_id, case_id, revision_id)
  references public.case_revisions (organization_id, case_id, revision_id)
  on delete cascade;

alter table public.approval_bindings
  add constraint approval_bindings_org_revision_fk
  foreign key (organization_id, case_id, revision_id)
  references public.case_revisions (organization_id, case_id, revision_id),
  add constraint approval_bindings_org_supersedes_fk
  foreign key (organization_id, case_id, supersedes_approval_id)
  references public.approval_bindings (organization_id, case_id, id);

alter table public.domain_events
  add constraint domain_events_org_case_fk
  foreign key (organization_id, case_id)
  references public.covenant_cases (organization_id, id)
  on delete cascade,
  add constraint domain_events_org_revision_fk
  foreign key (organization_id, case_id, revision_id)
  references public.case_revisions (organization_id, case_id, revision_id);

alter table public.revision_run_jobs
  add constraint revision_run_jobs_org_revision_fk
  foreign key (organization_id, case_id, revision_id)
  references public.case_revisions (organization_id, case_id, revision_id);

-- Exact approval and content-addressing invariants.
alter table public.case_revisions
  add constraint case_revisions_hash_format_check check (
    input_bundle_hash ~ '^[0-9a-f]{64}$'
    and rulebook_hash ~ '^[0-9a-f]{64}$'
    and mapping_hash ~ '^[0-9a-f]{64}$'
    and (calculation_hash is null or calculation_hash ~ '^[0-9a-f]{64}$')
    and (coverage_hash is null or coverage_hash ~ '^[0-9a-f]{64}$')
    and (package_hash is null or package_hash ~ '^[0-9a-f]{64}$')
  );

alter table public.review_decisions
  add constraint review_decisions_request_hash_check
    check (request_hash ~ '^[0-9a-f]{64}$');

alter table public.artifacts
  add constraint artifacts_content_hash_check
    check (content_hash ~ '^[0-9a-f]{64}$');

alter table public.approval_bindings
  add constraint approval_bindings_package_hash_check
    check (package_hash ~ '^[0-9a-f]{64}$'),
  add constraint approval_bindings_exact_numbers_check check (
    decision = 'rejected'
    or (
      approved_ratio is not null
      and approved_threshold is not null
      and approved_comparator is not null
      and approved_inputs <> '{}'::jsonb
    )
  );

-- Support FK checks and tenant-scoped policy lookups.
create index organizations_created_by_idx on public.organizations (created_by);
create index covenant_cases_created_by_idx on public.covenant_cases (created_by);
create index documents_created_by_idx on public.documents (created_by);
create index document_versions_uploaded_by_idx on public.document_versions (uploaded_by);
create index case_revisions_created_by_idx on public.case_revisions (created_by);
create index revision_documents_org_idx on public.revision_documents (organization_id);
create index change_sets_created_by_idx on public.change_sets (created_by);
create index impact_sets_org_idx on public.impact_sets (organization_id);
create index covenant_rules_org_idx on public.covenant_rules (organization_id);
create index covenant_rules_reviewed_by_idx on public.covenant_rules (reviewed_by);
create index financial_facts_org_idx on public.financial_facts (organization_id);
create index financial_facts_reviewed_by_idx on public.financial_facts (reviewed_by);
create index review_issues_org_idx on public.review_issues (organization_id);
create index review_decisions_actor_idx on public.review_decisions (actor_id);
create index artifacts_org_idx on public.artifacts (organization_id);
create index approval_bindings_org_idx on public.approval_bindings (organization_id);
create index approval_bindings_actor_idx on public.approval_bindings (actor_id);
create index domain_events_org_idx on public.domain_events (organization_id);

-- Protect source and decision history from normal backend mutations. A future
-- retention workflow must explicitly set this transaction-local maintenance flag.
create or replace function public.covenant_reject_immutable_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if current_setting('app.allow_immutable_maintenance', true) = 'on' then
    if tg_op = 'DELETE' then
      return old;
    end if;
    return new;
  end if;
  raise exception '% is append-only', tg_table_name
    using errcode = '55000';
end
$$;

create trigger document_versions_append_only
  before update or delete on public.document_versions
  for each row execute function public.covenant_reject_immutable_mutation();
create trigger review_decisions_append_only
  before update or delete on public.review_decisions
  for each row execute function public.covenant_reject_immutable_mutation();
create trigger approval_bindings_append_only
  before update or delete on public.approval_bindings
  for each row execute function public.covenant_reject_immutable_mutation();
create trigger domain_events_append_only
  before update or delete on public.domain_events
  for each row execute function public.covenant_reject_immutable_mutation();

revoke execute on function public.covenant_set_updated_at() from public, anon, authenticated;
revoke execute on function public.covenant_reject_immutable_mutation()
  from public, anon, authenticated;

-- Make Data API access deterministic even on projects with legacy defaults.
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke execute on all functions in schema public from anon, authenticated;

grant usage on schema public to authenticated;
grant select on public.organizations, public.organization_members,
  public.covenant_cases, public.documents, public.document_versions,
  public.case_revisions, public.revision_documents, public.change_sets,
  public.impact_sets, public.covenant_rules, public.financial_facts,
  public.review_issues, public.review_decisions, public.artifacts,
  public.approval_bindings, public.domain_events to authenticated;
grant insert on public.covenant_cases, public.documents,
  public.document_versions to authenticated;

alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke execute on functions from anon, authenticated;
