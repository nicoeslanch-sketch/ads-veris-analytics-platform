-- Aggregate counters only: no user IDs, URLs, filenames, queries or payloads.
create table app_private.operational_samples (
  instance_id uuid primary key,
  updated_at timestamptz not null default now(),
  requests bigint not null check (requests between 0 and 1000000000),
  errors bigint not null check (errors between 0 and requests),
  limited bigint not null check (limited between 0 and requests),
  slow bigint not null check (slow between 0 and requests)
);
alter table app_private.operational_samples enable row level security;
revoke all on app_private.operational_samples from public, anon, authenticated;
grant select, insert, update, delete on app_private.operational_samples to service_role;

create function public.operational_health(
  p_action text default 'snapshot', p_instance_id uuid default null,
  p_sample jsonb default '{}'::jsonb
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_http jsonb; v_queue jsonb; v_storage jsonb; v_limits jsonb;
begin
  if p_action = 'heartbeat' then
    if p_instance_id is null then raise exception 'Missing instance' using errcode='22023'; end if;
    -- Short lock bounds the table even if many instances register together.
    perform pg_advisory_xact_lock(831692301);
    delete from app_private.operational_samples where updated_at < now() - interval '10 minutes';
    if not exists(select 1 from app_private.operational_samples where instance_id=p_instance_id)
       and (select count(*) from app_private.operational_samples) >= 128 then
      raise exception 'Monitor instance limit' using errcode='22023';
    end if;
    insert into app_private.operational_samples(instance_id, requests, errors, limited, slow)
    values(p_instance_id,(p_sample->>'requests')::bigint,(p_sample->>'errors')::bigint,
      (p_sample->>'limited')::bigint,(p_sample->>'slow')::bigint)
    on conflict(instance_id) do update set updated_at=now(), requests=excluded.requests,
      errors=excluded.errors, limited=excluded.limited, slow=excluded.slow;
  elsif p_action <> 'snapshot' then
    raise exception 'Invalid monitor action' using errcode='22023';
  end if;
  select jsonb_build_object('instances',count(*),'requests',coalesce(sum(requests),0),
    'errors',coalesce(sum(errors),0),'limited',coalesce(sum(limited),0),
    'slow',coalesce(sum(slow),0),'window_seconds',300,
    'last_seen_at',max(updated_at)) into v_http
    from app_private.operational_samples where updated_at >= now() - interval '2 minutes';
  select jsonb_build_object('queued',count(*) filter(where status='queued'),
    'running',count(*) filter(where status='running'),
    'expired_leases',count(*) filter(where status='running' and lease_until<now()),
    'long_running',count(*) filter(where status='running' and started_at<now()-interval '20 minutes'),
    'failed_retained_15m',count(*) filter(where status='failed' and updated_at>=now()-interval '15 minutes'),
    'oldest_wait_seconds',coalesce(max(extract(epoch from now()-created_at)) filter(where status='queued'),0))
    into v_queue from app_private.analysis_queue_jobs;
  select jsonb_build_object('max_active',max_active,'max_running',max_running)
    into v_limits from app_private.analysis_queue_limits where singleton;
  select jsonb_build_object('used_bytes',coalesce(sum(coalesce((metadata->>'size')::bigint,67108864)),0),
    'objects',count(*),'unknown_sizes',count(*) filter(where metadata->>'size' is null),
    'limit_bytes',(select project_bytes from app_private.storage_budget where id),
    'reserved_bytes',(select coalesce(sum(greatest(r.bytes-coalesce((o.metadata->>'size')::bigint,0),0)),0)
      from app_private.storage_reservations r left join storage.objects o on o.bucket_id='datasets' and o.name=r.path),
    'stale_reservations',(select count(*) from app_private.storage_reservations where created_at<now()-interval '30 minutes'))
    into v_storage from storage.objects where bucket_id='datasets';
  return jsonb_build_object('sampled_at',now(),'http',v_http,'queue',v_queue || v_limits,'storage',v_storage);
end $$;
revoke all on function public.operational_health(text,uuid,jsonb) from public, anon, authenticated;
grant execute on function public.operational_health(text,uuid,jsonb) to service_role;
