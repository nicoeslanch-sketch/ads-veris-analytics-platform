begin;

create index account_erasure_target_idx on app_private.account_erasure_jobs(target_user_id)
  where target_user_id is not null;

-- Reserve/queue RPCs already hold these budget locks. Erasure takes them in
-- the same order before admission, so a late writer cannot evade the drain.
create function app_private.reject_erasing_account_write() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if exists(select 1 from app_private.account_erasure_jobs where target_user_id=new.user_id) then
    raise exception 'Account erasure in progress' using errcode='42501';
  end if;
  return new;
end;
$$;
revoke all on function app_private.reject_erasing_account_write() from public,anon,authenticated;
create trigger reject_erasing_account_storage before insert on app_private.storage_reservations
  for each row execute function app_private.reject_erasing_account_write();
create trigger reject_erasing_account_queue before insert or update of status on app_private.analysis_queue_jobs
  for each row when (new.status in ('queued','running'))
  execute function app_private.reject_erasing_account_write();

create or replace function app_private.account_session_active(p_user_id uuid, p_session_id uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from auth.sessions s join auth.users u on u.id=s.user_id
    where s.id=p_session_id and s.user_id=p_user_id
      and (s.not_after is null or s.not_after>now())
      and u.deleted_at is null and (u.banned_until is null or u.banned_until<=now())
  ) and not exists(select 1 from app_private.account_erasure_jobs where target_user_id=p_user_id);
$$;

create or replace function public.account_erasure_control(
  p_admin_id uuid, p_request_id uuid, p_action text, p_payload jsonb default '{}'::jsonb
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  req public.privacy_requests%rowtype;
  job app_private.account_erasure_jobs%rowtype;
  pending_writes integer;
  active_jobs integer;
begin
  if not exists(select 1 from public.profiles where id=p_admin_id and is_admin) then
    raise exception 'Admin required' using errcode='42501';
  end if;
  if p_action is null or p_action not in ('prepare','ready','storage_deleted','fail','complete','status') then
    raise exception 'Invalid erasure action' using errcode='22023';
  end if;
  -- Serialize queue admission, reservations and duplicate erasure requests.
  perform singleton from app_private.analysis_queue_limits where singleton for update;
  perform id from app_private.storage_budget where id for update;
  perform pg_advisory_xact_lock(hashtextextended('erasure:' || p_request_id::text,0));
  select * into job from app_private.account_erasure_jobs where request_id=p_request_id for update;
  if not found then
    if p_action<>'prepare' then raise exception 'Erasure job not found' using errcode='P0002'; end if;
    select * into req from public.privacy_requests where id=p_request_id for update;
    if not found or req.kind<>'erasure' or req.status not in ('pending','reviewing') then
      raise exception 'Open erasure request not found' using errcode='P0002';
    end if;
    if req.user_id=p_admin_id or exists(select 1 from public.profiles where id=req.user_id and is_admin) then
      raise exception 'Administrator erasure requires role transfer first' using errcode='22023';
    end if;
    if exists(select 1 from app_private.account_erasure_jobs where target_user_id=req.user_id) then
      raise exception 'Account already has an erasure job' using errcode='22023';
    end if;
    insert into app_private.account_erasure_jobs(request_id,target_user_id,subject_digest,initiated_by)
      values(req.id,req.user_id,encode(extensions.digest(req.user_id::text,'sha256'),'hex'),p_admin_id)
      returning * into job;
    update public.privacy_requests set status='reviewing',response='Eliminacion integral en ejecucion.',updated_at=now()
      where id=req.id;
    insert into public.admin_audit(admin_id,target_user_id,action,detail)
      values(p_admin_id,req.user_id,'account_erasure_started',jsonb_build_object('request_id',req.id,'job_id',job.id));
  end if;
  if p_action='status' or job.status='completed' then return to_jsonb(job); end if;
  if job.target_user_id=p_admin_id or exists(select 1 from public.profiles where id=job.target_user_id and is_admin) then
    raise exception 'Administrator erasure requires role transfer first' using errcode='22023';
  end if;
  if p_action='prepare' then
    -- Retry always re-verifies Storage, including a crash after Auth deletion.
    update app_private.account_erasure_jobs set status='deleting_storage',failed_stage=null,last_error=null,
      attempt_count=attempt_count+1,updated_at=now() where id=job.id returning * into job;
    update app_private.analysis_queue_jobs set cancel_requested=true,
      status='cancelled',phase='cancelled',result=null,lease_token=null,lease_until=null,updated_at=now()
      where user_id=job.target_user_id and status='queued';
    update app_private.analysis_queue_jobs set cancel_requested=true,phase='cancelling',updated_at=now()
      where user_id=job.target_user_id and status='running';
  elsif p_action='fail' then
    update app_private.account_erasure_jobs set status='failed',
      failed_stage=case when p_payload->>'stage'='deleting_storage' then 'deleting_storage' else 'deleting_account' end,
      last_error=left(coalesce(p_payload->>'error','Unknown failure'),500),updated_at=now()
      where id=job.id returning * into job;
    return to_jsonb(job);
  end if;

  select count(*) into pending_writes from app_private.storage_reservations where user_id=job.target_user_id;
  select count(*) into active_jobs from app_private.analysis_queue_jobs
    where user_id=job.target_user_id and status in ('queued','running');
  if p_action='ready' then
    return to_jsonb(job) || jsonb_build_object('ready',pending_writes=0 and active_jobs=0,
      'pending_writes',pending_writes,'active_jobs',active_jobs);
  end if;
  if p_action in ('storage_deleted','complete') then
    if pending_writes>0 or active_jobs>0 or exists(select 1 from storage.objects
      where bucket_id='datasets' and split_part(name,'/',1)=job.target_user_id::text) then
      raise exception 'Account still has files or active writes' using errcode='22023';
    end if;
    if job.status not in ('deleting_storage','deleting_account') then
      raise exception 'Erasure job needs preparation' using errcode='22023';
    end if;
    if p_action='storage_deleted' then
      update app_private.account_erasure_jobs set status='deleting_account',
        storage_objects_deleted=greatest(storage_objects_deleted,coalesce((p_payload->>'count')::integer,0)),
        failed_stage=null,last_error=null,updated_at=now() where id=job.id returning * into job;
    else
      if job.status<>'deleting_account' or exists(select 1 from auth.users where id=job.target_user_id) then
        raise exception 'Auth deletion has not been verified' using errcode='22023';
      end if;
      insert into public.admin_audit(admin_id,target_user_id,action,detail)
        values(p_admin_id,job.target_user_id,'account_erasure_completed',jsonb_build_object(
          'request_id',job.request_id,'job_id',job.id,'storage_objects_deleted',job.storage_objects_deleted));
      update app_private.account_erasure_jobs set status='completed',target_user_id=null,
        failed_stage=null,last_error=null,updated_at=now(),completed_at=now() where id=job.id returning * into job;
    end if;
  end if;
  return to_jsonb(job);
end;
$$;

create function public.admin_account_erasures(p_admin_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  if not exists(select 1 from public.profiles where id=p_admin_id and is_admin) then
    raise exception 'Admin required' using errcode='42501';
  end if;
  return coalesce((select jsonb_agg(to_jsonb(j)) from (
    select id,request_id,status,failed_stage,attempt_count,created_at,updated_at,completed_at
    from app_private.account_erasure_jobs order by created_at desc limit 100
  ) j),'[]'::jsonb);
end;
$$;
revoke all on function public.admin_account_erasures(uuid) from public,anon,authenticated;
grant execute on function public.admin_account_erasures(uuid) to service_role;
commit;
