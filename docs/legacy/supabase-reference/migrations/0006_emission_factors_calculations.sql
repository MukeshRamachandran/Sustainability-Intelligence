begin;
create table app_private.emission_factor_sets(
 id uuid primary key default gen_random_uuid(), version_label text not null unique,
 status app_private.factor_set_status not null default 'draft', jurisdiction text,
 source_citation text, valid_from date not null, valid_to date,
 proposed_by uuid references auth.users(id), approved_by uuid references auth.users(id), approved_at timestamptz,
 check(valid_to is null or valid_to>=valid_from),
 check(status<>'active' or (approved_by is not null and approved_at is not null and jurisdiction is not null and source_citation is not null))
);
create table app_private.emission_factors(
 id uuid primary key default gen_random_uuid(), factor_set_id uuid not null references app_private.emission_factor_sets(id) on delete restrict,
 code text not null, value numeric(20,9) not null check(value>=0), input_unit text not null,
 output_unit text not null default 'kgCO2e', scope smallint not null check(scope in (1,2)), method text not null,
 unique(factor_set_id,code)
);
create table app_private.approval_calculations(
 id uuid primary key default gen_random_uuid(), submission_id uuid not null references app_private.submissions(id) on delete restrict,
 metric_code text not null, activity_value numeric(20,6) not null, activity_unit text not null,
 factor_id uuid not null references app_private.emission_factors(id), factor_value numeric(20,9) not null,
 result_kgco2e numeric(20,6) not null, formula_version text not null, calculated_at timestamptz not null default now(),
 unique(submission_id,metric_code)
);
create or replace function app_private.block_active_factor_mutation() returns trigger language plpgsql security definer
set search_path=pg_catalog,app_private as $$ begin
 if exists(select 1 from app_private.emission_factor_sets s where s.id=coalesce(new.factor_set_id,old.factor_set_id) and s.status<>'draft')
 then raise exception 'non-draft factor immutable' using errcode='42501'; end if;
 if tg_op='DELETE' then return old; else return new; end if;
end $$;
create trigger factor_immutable before update or delete on app_private.emission_factors for each row execute function app_private.block_active_factor_mutation();
revoke all on app_private.emission_factor_sets,app_private.emission_factors,app_private.approval_calculations from public,anon,authenticated;
alter table app_private.emission_factor_sets enable row level security; alter table app_private.emission_factor_sets force row level security;
alter table app_private.emission_factors enable row level security; alter table app_private.emission_factors force row level security;
alter table app_private.approval_calculations enable row level security; alter table app_private.approval_calculations force row level security;
create policy factor_sets_read on app_private.emission_factor_sets for select to authenticated using(app_private.is_verified_active_user(auth.uid()));
create policy factors_read on app_private.emission_factors for select to authenticated using(app_private.is_verified_active_user(auth.uid()));
create policy calculations_read on app_private.approval_calculations for select to authenticated using
 (app_private.has_role('administrator') or exists(select 1 from app_private.submissions s where s.id=submission_id and s.submitter_id=auth.uid()));
grant select on app_private.emission_factor_sets,app_private.emission_factors,app_private.approval_calculations to authenticated;
commit;
