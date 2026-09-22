begin;

create or replace function app_private.transition_submission(
  target_id uuid, expected_version integer, requested app_private.submission_status, reason text default null)
returns app_private.submissions language plpgsql security definer
set search_path=pg_catalog,auth,app_private as $$
declare s app_private.submissions; action app_private.review_action; prior app_private.submission_status;
begin
  select * into s from app_private.submissions where id=target_id for update;
  if not found or s.row_version<>expected_version then raise exception 'not found or stale version' using errcode='40001'; end if;
  if not app_private.is_verified_active_user(auth.uid()) then raise exception 'verified active user required' using errcode='42501'; end if;
  prior:=s.status;
  if requested='submitted' then
   s.revision:=s.revision+1;
   insert into app_private.submission_revisions(submission_id,revision,actor_id,reason,snapshot)
   select s.id,s.revision,auth.uid(),coalesce(reason,requested::text),jsonb_build_object('submission',to_jsonb(s),
    'values',coalesce((select jsonb_agg(to_jsonb(v) order by v.metric_code) from app_private.submission_values v where v.submission_id=s.id),'[]'::jsonb));
  end if;
  if requested in ('submitted') then
    if s.submitter_id<>auth.uid() or not app_private.has_domain(s.domain) or s.status not in ('draft','correction_requested') then raise exception 'transition denied' using errcode='42501'; end if;
    if exists(select 1 from app_private.submission_values v join app_private.metric_definitions m on m.code=v.metric_code
      where v.submission_id=s.id and m.domain<>s.domain) then raise exception 'cross-domain metric'; end if;
    if exists(select 1 from app_private.metric_definitions m where m.domain=s.domain and m.required_for_complete
      and not exists(select 1 from app_private.submission_values v where v.submission_id=s.id and v.metric_code=m.code and v.value is not null))
      then raise exception 'required values missing'; end if;
    action:=case when s.status='draft' then 'submitted' else 'resubmitted' end;
  elsif requested='under_review' then
    if not app_private.is_admin_mfa() or s.status<>'submitted' then raise exception 'transition denied' using errcode='42501'; end if;
    action:='review_started';
  elsif requested='correction_requested' then
    if not app_private.is_admin_mfa() or s.status<>'under_review' or length(trim(reason))=0 then raise exception 'reason/admin MFA review required' using errcode='42501'; end if;
    action:='correction_requested';
  else raise exception 'approval uses approve_submission';
  end if;
  update app_private.submissions set status=requested,revision=s.revision,row_version=row_version+1,updated_at=now(),
    submitted_at=case when requested='submitted' then now() else submitted_at end where id=s.id returning * into s;
  insert into app_private.review_actions(submission_id,action,reviewer_id,from_status,to_status,reason)
    values(s.id,action,auth.uid(),prior,requested,reason);
  insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
    values(auth.uid(),'user','submission.'||requested,'submission',s.id::text,'succeeded',jsonb_build_object('row_version',s.row_version));
  return s;
end $$;

revoke all on function app_private.transition_submission(uuid,integer,app_private.submission_status,text) from public,anon;
grant execute on function app_private.transition_submission(uuid,integer,app_private.submission_status,text) to authenticated;
commit;
