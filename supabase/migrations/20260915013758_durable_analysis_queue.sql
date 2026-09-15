-- Private, bounded queue. Only the authenticated API and trusted worker call
-- this RPC using service_role; browser roles never receive queue access.
create table app_private.analysis_queue_limits (
  singleton boolean primary key default true check (singleton),
  max_active integer not null default 32 check (max_active between 1 and 128),
  max_user_active integer not null default 3 check (max_user_active between 1 and 10),
  max_running integer not null default 1 check (max_running between 1 and 16)
);
insert into app_private.analysis_queue_limits(singleton) values (true);
create table app_private.analysis_queue_jobs (
  job_id text primary key check (job_id ~ '^dq_[0-9a-f]{32}$'),
  user_id uuid not null references auth.users(id) on delete cascade,
  dataset_id uuid not null references public.datasets(id) on delete cascade,
  source_path text not null,
  source_object_id uuid not null,
  engine_version text not null,
  kind text not null check (kind in ('metrics','standardize_batch','clean_batch','clean_export')),
  options jsonb not null check (jsonb_typeof(options)='object' and octet_length(options::text)<=262144),
  status text not null default 'queued' check (status in ('queued','running','completed','failed','cancelled')),
  phase text not null default 'queued',
  attempt integer not null default 0,
  completed_phases integer not null default 0,
  total_phases integer not null default 1,
  current_sheet text,
  cancel_requested boolean not null default false,
  lease_token uuid,
  lease_until timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  started_at timestamptz,
  result jsonb check (result is null or octet_length(result::text)<=2097152),
  error text
);
create index analysis_queue_owner on app_private.analysis_queue_jobs(user_id,created_at);
create index analysis_queue_dataset on app_private.analysis_queue_jobs(dataset_id);
create index analysis_queue_pending on app_private.analysis_queue_jobs(engine_version,created_at)
  where status in ('queued','running');
alter table app_private.analysis_queue_limits enable row level security;
alter table app_private.analysis_queue_jobs enable row level security;
revoke all on app_private.analysis_queue_limits,app_private.analysis_queue_jobs from public,anon,authenticated;
grant select,insert,update,delete on app_private.analysis_queue_limits,app_private.analysis_queue_jobs to service_role;

create function public.analysis_queue(
  p_action text, p_user_id uuid default null, p_job_id text default null,
  p_payload jsonb default '{}'::jsonb, p_token uuid default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  j app_private.analysis_queue_jobs%rowtype;
  lim app_private.analysis_queue_limits%rowtype;
  object_id uuid;
  n integer;
begin
  if p_action = 'get' then
    select * into j from app_private.analysis_queue_jobs where job_id=p_job_id and user_id=p_user_id;
    return case when found then to_jsonb(j) else null end;
  end if;
  -- One short lock serializes admission, claim, cancellation and publication.
  -- No network or processing work is performed while holding it.
  select * into strict lim from app_private.analysis_queue_limits where singleton for update;
  if p_action in ('enqueue','claim','retry') then
    delete from app_private.analysis_queue_jobs where status in ('completed','failed','cancelled')
      and updated_at < now()-interval '24 hours';
    update app_private.analysis_queue_jobs set
      status=case when cancel_requested then 'cancelled' when attempt>=3 then 'failed' else 'queued' end,
      phase=case when cancel_requested then 'cancelled' when attempt>=3 then 'failed' else 'recovering' end,
      error=case when attempt>=3 then 'El proceso se interrumpio varias veces. Revisa el archivo antes de reintentar.' else null end,
      lease_token=null,lease_until=null,updated_at=now()
      where status='running' and lease_until<now();
  end if;
  if p_action='enqueue' then
    select s.id into object_id from storage.objects s join public.datasets d
      on d.storage_path=s.name and d.id=(p_payload->>'dataset_id')::uuid
      where s.bucket_id='datasets' and s.name=p_payload->>'source_path' and d.user_id=p_user_id
        and split_part(s.name,'/',1)=p_user_id::text;
    if not found then return jsonb_build_object('rejected',404,'detail','El archivo guardado no existe o no pertenece a tu cuenta.'); end if;
    select * into j from app_private.analysis_queue_jobs where job_id=p_job_id and user_id=p_user_id;
    if found then return to_jsonb(j); end if;
    select count(*) into n from app_private.analysis_queue_jobs where status in ('queued','running');
    if n>=lim.max_active or (select count(*) from app_private.analysis_queue_jobs where user_id=p_user_id and status in ('queued','running'))>=lim.max_user_active then
      return jsonb_build_object('rejected',429,'detail','La cola esta ocupada. Espera a que termine un trabajo antes de iniciar otro.');
    end if;
    -- Results are an operational cache, not a customer archive. Bound its rows.
    delete from app_private.analysis_queue_jobs where job_id in (
      select job_id from app_private.analysis_queue_jobs where status in ('completed','failed','cancelled')
      order by updated_at desc offset 63
    );
    insert into app_private.analysis_queue_jobs(job_id,user_id,dataset_id,source_path,source_object_id,engine_version,kind,options)
      values(p_job_id,p_user_id,(p_payload->>'dataset_id')::uuid,p_payload->>'source_path',object_id,
        p_payload->>'engine_version',p_payload->>'kind',p_payload->'options') returning * into j;
    return to_jsonb(j);
  elsif p_action='claim' then
    if (select count(*) from app_private.analysis_queue_jobs where status='running')>=lim.max_running then return null; end if;
    select q.* into j from app_private.analysis_queue_jobs q
      where q.status='queued' and q.engine_version=p_payload->>'engine_version'
        and not exists(select 1 from app_private.analysis_queue_jobs r where r.user_id=q.user_id and r.status='running')
      order by (select max(r.started_at) from app_private.analysis_queue_jobs r where r.user_id=q.user_id) nulls first,q.created_at
      limit 1 for update of q skip locked;
    if not found then return null; end if;
    update app_private.analysis_queue_jobs set status='running',phase='starting',attempt=attempt+1,
      started_at=now(),updated_at=now(),lease_token=gen_random_uuid(),lease_until=now()+interval '120 seconds'
      where job_id=j.job_id returning * into j;
    return to_jsonb(j);
  end if;

  select * into j from app_private.analysis_queue_jobs where job_id=p_job_id and user_id=p_user_id for update;
  if not found then return null; end if;
  if p_action='cancel' then
    if j.status in ('queued','running') then
      update app_private.analysis_queue_jobs set cancel_requested=true,
        status=case when status='queued' then 'cancelled' else status end,
        phase=case when status='queued' then 'cancelled' else 'cancelling' end,updated_at=now()
        where job_id=p_job_id returning * into j;
    end if;
    return to_jsonb(j);
  elsif p_action='retry' then
    if j.status in ('failed','cancelled') then
      if j.attempt>=3 then return jsonb_build_object('rejected',409,'detail','Se alcanzo el limite de intentos. Revisa la causa antes de crear otro proceso.'); end if;
      if (select count(*) from app_private.analysis_queue_jobs where status in ('queued','running'))>=lim.max_active
        or (select count(*) from app_private.analysis_queue_jobs where user_id=p_user_id and status in ('queued','running'))>=lim.max_user_active then
        return jsonb_build_object('rejected',429,'detail','La cola esta ocupada. Espera a que termine un trabajo.');
      end if;
      update app_private.analysis_queue_jobs set status='queued',phase='queued',cancel_requested=false,
        result=null,error=null,completed_phases=0,updated_at=now() where job_id=p_job_id returning * into j;
    end if;
    return to_jsonb(j);
  end if;
  -- A stale worker can neither extend its lease nor publish a late result.
  if j.status<>'running' or p_token is null or j.lease_token<>p_token or j.lease_until<now() then return null; end if;
  if p_action in ('heartbeat','progress') then
    if j.started_at<now()-interval '20 minutes' then
      update app_private.analysis_queue_jobs set cancel_requested=true,phase='cancelling',updated_at=now() where job_id=p_job_id returning * into j;
      return to_jsonb(j);
    end if;
    update app_private.analysis_queue_jobs set lease_until=now()+interval '120 seconds',updated_at=now(),
      phase=case when cancel_requested then 'cancelling' else coalesce(p_payload->>'phase',phase) end,
      completed_phases=coalesce((p_payload->>'completed_phases')::integer,completed_phases),
      total_phases=coalesce((p_payload->>'total_phases')::integer,total_phases),
      current_sheet=coalesce(p_payload->>'current_sheet',current_sheet)
      where job_id=p_job_id returning * into j;
    return to_jsonb(j);
  elsif p_action='source' then
    if not exists(select 1 from storage.objects s join public.datasets d on d.id=j.dataset_id and d.storage_path=s.name
      where s.id=j.source_object_id and s.name=j.source_path and d.user_id=j.user_id and s.bucket_id='datasets') then
      return jsonb_build_object('rejected',404,'detail','La fuente se elimino o cambio desde que se encolo el trabajo.');
    end if;
    return to_jsonb(j);
  elsif p_action='finish' then
    if p_payload->>'status' not in ('completed','failed','cancelled') then raise exception 'invalid terminal status'; end if;
    if octet_length(coalesce((p_payload->'result')::text,''))>2097152 then
      p_payload=jsonb_build_object('status','failed','error','El resultado supera el limite de la cola. Reduce el alcance del analisis.');
    end if;
    -- Cap result bytes independently of the count of jobs (32 MiB project).
    while coalesce((select sum(octet_length(result::text)) from app_private.analysis_queue_jobs),0)
      +octet_length(coalesce((p_payload->'result')::text,''))>33554432 loop
      delete from app_private.analysis_queue_jobs where job_id=(select job_id from app_private.analysis_queue_jobs
        where status in ('completed','failed','cancelled') and result is not null order by updated_at limit 1);
      exit when not found;
    end loop;
    update app_private.analysis_queue_jobs set
      status=case when cancel_requested then 'cancelled' else p_payload->>'status' end,
      phase=case when cancel_requested then 'cancelled' else p_payload->>'status' end,
      result=case when not cancel_requested and p_payload->>'status'='completed' then p_payload->'result' else null end,
      error=left(p_payload->>'error',500),lease_token=null,lease_until=null,updated_at=now(),
      completed_phases=case when p_payload->>'status'='completed' and not cancel_requested then total_phases else completed_phases end
      where job_id=p_job_id returning * into j;
    return to_jsonb(j);
  end if;
  raise exception 'invalid queue action';
end;
$$;
revoke all on function public.analysis_queue(text,uuid,text,jsonb,uuid) from public,anon,authenticated;
grant execute on function public.analysis_queue(text,uuid,text,jsonb,uuid) to service_role;
