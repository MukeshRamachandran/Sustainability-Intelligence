begin;

create table app_private.evidence_upload_authorizations (
  id uuid primary key default gen_random_uuid(),
  submission_id uuid not null references app_private.submissions(id) on delete cascade,
  uploader_id uuid not null references auth.users(id) on delete restrict,
  object_path text not null unique check (object_path !~ '(^|/)\.\.(/|$)'),
  expected_mime text not null check (expected_mime in ('application/pdf','image/png')),
  max_bytes bigint not null default 10485760 check (max_bytes between 1 and 10485760),
  status app_private.evidence_status not null default 'pending' check (status in ('pending','uploading','failed')),
  idempotency_key uuid not null unique,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  created_at timestamptz not null default now()
);
create table app_private.evidence_files (
  id uuid primary key default gen_random_uuid(),
  authorization_id uuid not null unique references app_private.evidence_upload_authorizations(id) on delete restrict,
  submission_id uuid not null references app_private.submissions(id) on delete restrict,
  uploader_id uuid not null references auth.users(id) on delete restrict,
  bucket_id text not null default 'submission-evidence' check (bucket_id='submission-evidence'),
  object_path text not null unique,
  original_name text not null,
  detected_mime text check (detected_mime in ('application/pdf','image/png')),
  byte_size bigint check (byte_size between 1 and 10485760),
  sha256 text check (sha256 is null or sha256 ~ '^[0-9a-f]{64}$'),
  status app_private.evidence_status not null default 'quarantined' check (status in ('quarantined','clean','failed','infected','deleted')),
  uploaded_at timestamptz not null default now(),
  validated_at timestamptz,
  retention_until date not null default (current_date + interval '7 years')::date
);

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('submission-evidence','submission-evidence',false,10485760,array['application/pdf','image/png'])
on conflict(id) do update set public=false,file_size_limit=10485760,allowed_mime_types=excluded.allowed_mime_types;

revoke all on app_private.evidence_upload_authorizations,app_private.evidence_files from public,anon,authenticated;
alter table app_private.evidence_upload_authorizations enable row level security; alter table app_private.evidence_upload_authorizations force row level security;
alter table app_private.evidence_files enable row level security; alter table app_private.evidence_files force row level security;
create policy evidence_auth_read on app_private.evidence_upload_authorizations for select to authenticated
 using (uploader_id=auth.uid() or app_private.has_role('administrator'));
create policy evidence_read on app_private.evidence_files for select to authenticated using
 (status='clean' and (uploader_id=auth.uid() or app_private.has_role('administrator')));
grant select on app_private.evidence_upload_authorizations,app_private.evidence_files to authenticated;

create or replace function app_private.claim_evidence_upload(auth_id uuid, idem uuid)
returns text language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$
declare a app_private.evidence_upload_authorizations;
begin
 update app_private.evidence_upload_authorizations set status='uploading'
 where id=auth_id and uploader_id=auth.uid() and status='pending' and idempotency_key=idem and expires_at>now()
 returning * into a;
 if not found then raise exception 'upload authorization unavailable' using errcode='42501'; end if;
 if not exists(select 1 from app_private.submissions s where s.id=a.submission_id and s.submitter_id=auth.uid()
   and app_private.has_domain(s.domain) and s.status in ('draft','correction_requested')) then raise exception 'submission not uploadable' using errcode='42501'; end if;
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,correlation_id)
 values(auth.uid(),'user','evidence.upload_started','upload_authorization',a.id::text,'started',idem);
 return a.object_path;
end $$;
create or replace function app_private.finalize_evidence_upload(auth_id uuid,idem uuid,original_name text)
returns uuid language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$
declare a app_private.evidence_upload_authorizations; eid uuid;
begin
 select * into a from app_private.evidence_upload_authorizations where id=auth_id and uploader_id=auth.uid()
   and idempotency_key=idem and status='uploading' for update;
 if not found then select id into eid from app_private.evidence_files where authorization_id=auth_id; if eid is not null then return eid; end if; raise exception 'upload not claimable'; end if;
 if not exists(select 1 from storage.objects o where o.bucket_id='submission-evidence' and o.name=a.object_path)
 then raise exception 'uploaded object not found'; end if;
 insert into app_private.evidence_files(authorization_id,submission_id,uploader_id,object_path,original_name)
 values(a.id,a.submission_id,a.uploader_id,a.object_path,original_name) returning id into eid;
 update app_private.evidence_upload_authorizations set consumed_at=now() where id=a.id;
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,correlation_id)
 values(auth.uid(),'user','evidence.upload_finalized','evidence',eid::text,'succeeded',idem);
 return eid;
end $$;
revoke all on function app_private.claim_evidence_upload(uuid,uuid) from public,anon;
revoke all on function app_private.finalize_evidence_upload(uuid,uuid,text) from public,anon;
grant execute on function app_private.claim_evidence_upload(uuid,uuid) to authenticated;
grant execute on function app_private.finalize_evidence_upload(uuid,uuid,text) to authenticated;

drop policy if exists microcosm_evidence_read on storage.objects;
create policy microcosm_evidence_read on storage.objects for select to authenticated using
 (bucket_id='submission-evidence' and exists(select 1 from app_private.evidence_files e
  where e.bucket_id=storage.objects.bucket_id and e.object_path=storage.objects.name and e.status='clean'
  and (e.uploader_id=auth.uid() or app_private.has_role('administrator'))));
-- No authenticated INSERT/UPDATE/DELETE policy or table grant: controlled server upload only.
commit;
