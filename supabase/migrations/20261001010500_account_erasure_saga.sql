begin;

-- The receipt intentionally survives Auth deletion. It never stores email,
-- filenames, request text or customer data. The target UUID is removed after
-- completion and only a one-way digest remains for duplicate-proof evidence.
create table app_private.account_erasure_jobs (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null unique,
  target_user_id uuid,
  subject_digest text not null,
  initiated_by uuid not null,
  status text not null default 'pending'
    check (status in ('pending','deleting_storage','deleting_account','completed','failed')),
  storage_objects_deleted integer not null default 0 check (storage_objects_deleted >= 0),
  failed_stage text check (failed_stage is null or failed_stage in ('deleting_storage','deleting_account')),
  last_error text check (last_error is null or length(last_error) <= 500),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz
);
alter table app_private.account_erasure_jobs enable row level security;
revoke all on app_private.account_erasure_jobs from public, anon, authenticated;
grant select, insert, update on app_private.account_erasure_jobs to service_role;

create function public.account_erasure_control(
  p_admin_id uuid,
  p_request_id uuid,
  p_action text,
  p_payload jsonb default '{}'::jsonb
) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  req public.privacy_requests%rowtype;
  job app_private.account_erasure_jobs%rowtype;
  target_admin boolean;
begin
  if not exists(select 1 from public.profiles where id=p_admin_id and is_admin) then
    raise exception 'Admin required' using errcode='42501';
  end if;
  if p_action not in ('prepare','storage_deleted','fail','complete','status') then
    raise exception 'Invalid erasure action' using errcode='22023';
  end if;

  select * into job from app_private.account_erasure_jobs
    where request_id=p_request_id for update;
  if not found then
    if p_action <> 'prepare' then
      raise exception 'Erasure job not found' using errcode='P0002';
    end if;
    select * into req from public.privacy_requests where id=p_request_id for update;
    if not found or req.kind <> 'erasure' or req.status not in ('pending','reviewing') then
      raise exception 'Open erasure request not found' using errcode='P0002';
    end if;
    if req.user_id=p_admin_id then
      raise exception 'Administrators cannot erase their own account here' using errcode='22023';
    end if;
    select coalesce(is_admin,false) into target_admin from public.profiles where id=req.user_id;
    if coalesce(target_admin,false) then
      raise exception 'Administrator erasure requires role transfer first' using errcode='22023';
    end if;
    insert into app_private.account_erasure_jobs(
      request_id,target_user_id,subject_digest,initiated_by,status,attempt_count
    ) values(
      req.id,req.user_id,encode(extensions.digest(req.user_id::text,'sha256'),'hex'),
      p_admin_id,'deleting_storage',1
    ) returning * into job;
    update public.privacy_requests set status='reviewing',
      response='Eliminacion integral en ejecucion.',updated_at=now() where id=req.id;
    update app_private.analysis_queue_jobs set cancel_requested=true,
      status=case when status='queued' then 'cancelled' else status end,
      phase=case when status='queued' then 'cancelled' else 'cancelling' end,
      updated_at=now()
      where user_id=req.user_id and status in ('queued','running');
    insert into public.admin_audit(admin_id,target_user_id,action,detail)
      values(p_admin_id,req.user_id,'account_erasure_started',
        jsonb_build_object('request_id',req.id,'job_id',job.id));
    return to_jsonb(job);
  end if;

  if p_action='status' or job.status='completed' then return to_jsonb(job); end if;
  if p_action='storage_deleted' then
    if job.status not in ('deleting_storage','failed') then
      raise exception 'Erasure job is not ready for storage completion' using errcode='22023';
    end if;
    update app_private.account_erasure_jobs set status='deleting_account',
      storage_objects_deleted=greatest(storage_objects_deleted,coalesce((p_payload->>'count')::integer,0)),
      failed_stage=null,last_error=null,updated_at=now() where id=job.id returning * into job;
  elsif p_action='fail' then
    update app_private.account_erasure_jobs set status='failed',
      failed_stage=case when p_payload->>'stage' in ('deleting_storage','deleting_account')
        then p_payload->>'stage' else 'deleting_account' end,
      last_error=left(coalesce(p_payload->>'error','Unknown failure'),500),
      attempt_count=attempt_count+1,updated_at=now() where id=job.id returning * into job;
  elsif p_action='complete' then
    if job.status not in ('deleting_account','failed') then
      raise exception 'Erasure job is not ready for completion' using errcode='22023';
    end if;
    insert into public.admin_audit(admin_id,target_user_id,action,detail)
      values(p_admin_id,job.target_user_id,'account_erasure_completed',
        jsonb_build_object('request_id',job.request_id,'job_id',job.id,
          'storage_objects_deleted',job.storage_objects_deleted));
    update app_private.account_erasure_jobs set status='completed',target_user_id=null,
      failed_stage=null,last_error=null,updated_at=now(),completed_at=now()
      where id=job.id returning * into job;
  end if;
  return to_jsonb(job);
end;
$$;
revoke all on function public.account_erasure_control(uuid,uuid,text,jsonb)
  from public, anon, authenticated;
grant execute on function public.account_erasure_control(uuid,uuid,text,jsonb) to service_role;

commit;
