-- Cases created from a catalog template (POST /api/cases) remember the
-- template id so the API can resolve rule/facts for a non-curated case id.
alter table public.covenant_cases
  add column if not exists template_case_id text;
