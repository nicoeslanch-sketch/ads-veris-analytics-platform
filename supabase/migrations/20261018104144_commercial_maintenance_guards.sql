-- Private, bounded maintenance state. No customer row is changed by this migration.
create table app_private.retention_guards (
  user_id uuid primary key references auth.users(id) on delete cascade,
  lease uuid not null,
  expires_at timestamptz not null
);
alter table app_private.retention_guards enable row level security;
revoke all on app_private.retention_guards from public, anon, authenticated;
grant select, insert, update, delete on app_private.retention_guards to service_role;
create function public.retention_guard(p_action text, p_user_id uuid, p_lease uuid default null)
returns uuid language plpgsql security invoker set search_path = '' as $$
declare token uuid;
begin
  if current_user not in ('service_role','postgres') then raise insufficient_privilege; end if;
  if p_action = 'claim' then
    insert into app_private.retention_guards(user_id,lease,expires_at)
      values(p_user_id,gen_random_uuid(),now() + interval '3 minutes')
      on conflict(user_id) do update set lease = gen_random_uuid(), expires_at = now() + interval '3 minutes'
        where app_private.retention_guards.expires_at < now()
      returning lease into token;
  elsif p_action = 'renew' then
    update app_private.retention_guards set expires_at = now() + interval '3 minutes'
      where user_id = p_user_id and lease = p_lease and expires_at > now() returning lease into token;
  elsif p_action = 'release' then
    delete from app_private.retention_guards where user_id = p_user_id and lease = p_lease returning lease into token;
  else raise invalid_parameter_value;
  end if;
  return token;
end $$;
revoke all on function public.retention_guard(text,uuid,uuid) from public, anon, authenticated;
grant execute on function public.retention_guard(text,uuid,uuid) to service_role;

create table app_private.retention_journal (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  object_name text not null check (length(object_name) between 1 and 1024 and object_name !~ '[/\\]'),
  object_id text not null check (length(object_id) between 1 and 128),
  object_stamp text not null check (length(object_stamp) <= 128),
  stage text not null default 'pending' check (stage in ('pending','storage_deleted','completed','cancelled')),
  updated_at timestamptz not null default now(),
  unique (user_id, object_name, object_id, object_stamp)
);
create index retention_journal_pending on app_private.retention_journal(user_id, updated_at)
  where stage in ('pending','storage_deleted');
alter table app_private.retention_journal enable row level security;
revoke all on app_private.retention_journal from public, anon, authenticated;
grant select, insert, update, delete on app_private.retention_journal to service_role;

create function public.retention_journal_operation(p_action text, p_user_id uuid,
  p_id uuid default null, p_name text default null, p_object_id text default null,
  p_stamp text default null, p_stage text default null)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare item app_private.retention_journal; result jsonb;
begin
  if current_user not in ('service_role','postgres') then raise insufficient_privilege; end if;
  if p_action = 'list' then
    select coalesce(jsonb_agg(to_jsonb(j)), '[]'::jsonb) into result from (
      select * from app_private.retention_journal where user_id = p_user_id
      and stage in ('pending','storage_deleted') order by updated_at, id limit 100
    ) j;
    return result;
  elsif p_action = 'begin' then
    if p_name is null or p_name in ('.','..') or p_name ~ '[/\\]' or p_object_id is null or p_stamp is null then
      raise invalid_parameter_value;
    end if;
    insert into app_private.retention_journal(user_id, object_name, object_id, object_stamp)
      values(p_user_id, p_name, p_object_id, p_stamp)
      on conflict (user_id, object_name, object_id, object_stamp) do update set updated_at = now(),
        stage = case when app_private.retention_journal.stage = 'cancelled' then 'pending' else app_private.retention_journal.stage end
      returning * into item;
    return to_jsonb(item);
  elsif p_action = 'advance' then
    if p_stage not in ('storage_deleted','completed','cancelled') or p_stage is null then raise invalid_parameter_value; end if;
    update app_private.retention_journal set stage = p_stage, updated_at = now()
      where id = p_id and user_id = p_user_id and
      (stage = p_stage or (stage = 'pending' and p_stage in ('storage_deleted','cancelled'))
       or (stage = 'storage_deleted' and p_stage in ('completed','cancelled')))
      returning * into item;
    if item.id is null then raise no_data_found; end if;
    return to_jsonb(item);
  end if;
  raise invalid_parameter_value;
end $$;
revoke all on function public.retention_journal_operation(text,uuid,uuid,text,text,text,text) from public, anon, authenticated;
grant execute on function public.retention_journal_operation(text,uuid,uuid,text,text,text,text) to service_role;

create table app_private.operational_notifications (
  destination text not null check (destination ~ '^[a-f0-9]{64}$'),
  code text not null check (code ~ '^[A-Z_]{3,40}$'),
  active boolean not null,
  revision bigint not null default 1,
  delivered_revision bigint not null default 0,
  lease uuid,
  lease_until timestamptz,
  next_attempt timestamptz not null default now(),
  failures integer not null default 0,
  updated_at timestamptz not null default now(),
  primary key (destination, code)
);
alter table app_private.operational_notifications enable row level security;
revoke all on app_private.operational_notifications from public, anon, authenticated;
grant select, insert, update, delete on app_private.operational_notifications to service_role;

create function public.operational_notification(p_action text, p_destination text,
  p_codes text[] default '{}', p_code text default null, p_lease uuid default null,
  p_revision bigint default null, p_success boolean default false)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare item app_private.operational_notifications; c text;
begin
  if current_user not in ('service_role','postgres') then raise insufficient_privilege; end if;
  if p_destination is null or p_destination !~ '^[a-f0-9]{64}$' then raise invalid_parameter_value; end if;
  if p_action = 'sync' then
    if p_codes is null or cardinality(p_codes) > 20 or exists (
      select 1 from unnest(p_codes) x where x is null or x not in (
        'MONITOR_STALE','MONITOR_UNAVAILABLE','HTTP_ERRORS','HTTP_LIMITED','HTTP_SLOW',
        'WORKER_STALLED','QUEUE_WAIT','QUEUE_PRESSURE','JOBS_FAILED','STORAGE_PRESSURE',
        'STORAGE_PENDING','STORAGE_UNKNOWN','RETENTION_PENDING','RETENTION_FAILED')) then raise invalid_parameter_value; end if;
    perform pg_advisory_xact_lock(hashtextextended('ops-notify:' || p_destination, 0));
    foreach c in array p_codes loop
      insert into app_private.operational_notifications(destination,code,active) values(p_destination,c,true)
      on conflict(destination,code) do update set active = true, revision = app_private.operational_notifications.revision + 1,
        lease = null, lease_until = null, next_attempt = now(), failures = 0, updated_at = now()
        where not app_private.operational_notifications.active;
    end loop;
    update app_private.operational_notifications set active = false, revision = revision + 1,
      lease = null, lease_until = null, next_attempt = now(), failures = 0, updated_at = now()
      where destination = p_destination and active and not (code = any(p_codes));
    return jsonb_build_object('ok',true);
  elsif p_action = 'claim' then
    select * into item from app_private.operational_notifications
      where destination = p_destination and revision > delivered_revision and next_attempt <= now()
      and (lease_until is null or lease_until < now())
      order by updated_at,code limit 1 for update skip locked;
    if item.code is null then return null; end if;
    update app_private.operational_notifications set lease = gen_random_uuid(), lease_until = now() + interval '90 seconds'
      where destination = item.destination and code = item.code returning * into item;
    return jsonb_build_object('code',item.code,'active',item.active,'revision',item.revision,'lease',item.lease);
  elsif p_action = 'ack' then
    update app_private.operational_notifications set
      delivered_revision = case when p_success then revision else delivered_revision end,
      failures = case when p_success then 0 else least(failures + 1,10) end,
      next_attempt = now() + make_interval(secs => case when p_success then 0 else least(900,60 * power(2,least(failures,4))::integer) end),
      lease = null, lease_until = null
      where destination = p_destination and code = p_code and lease = p_lease and revision = p_revision;
    return jsonb_build_object('acknowledged',found);
  end if;
  raise invalid_parameter_value;
end $$;
revoke all on function public.operational_notification(text,text,text[],text,uuid,bigint,boolean) from public, anon, authenticated;
grant execute on function public.operational_notification(text,text,text[],text,uuid,bigint,boolean) to service_role;

create table app_private.retention_schedule (
  id boolean primary key default true check(id),
  cursor_user uuid,
  lease uuid,
  next_scan timestamptz not null default now(),
  completed_at timestamptz,
  report jsonb not null default '{}'
);
insert into app_private.retention_schedule(id) values(true);
alter table app_private.retention_schedule enable row level security;
revoke all on app_private.retention_schedule from public, anon, authenticated;
grant select, update on app_private.retention_schedule to service_role;

create function public.retention_schedule_operation(p_action text, p_lease uuid default null, p_report jsonb default '{}')
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare state app_private.retention_schedule; users uuid[];
begin
  if current_user not in ('service_role','postgres') then raise insufficient_privilege; end if;
  select * into state from app_private.retention_schedule where id for update;
  if p_action = 'status' then
    return jsonb_build_object('completed_at',state.completed_at,'report',state.report);
  elsif p_action = 'claim' then
    if state.next_scan > now() then return null; end if;
    select array_agg(user_id order by user_id) into users from (
      select user_id from (
        select distinct user_id from public.datasets where storage_path is not null
        union select user_id from app_private.retention_journal where stage in ('pending','storage_deleted')
      ) owners where
      (state.cursor_user is null or user_id > state.cursor_user) order by user_id limit 5
    ) x;
    if users is null then
      update app_private.retention_schedule set cursor_user = null, next_scan = now() + interval '1 hour' where id;
      return null;
    end if;
    update app_private.retention_schedule set cursor_user = users[cardinality(users)],
      lease = gen_random_uuid(), next_scan = now() + interval '1 hour' where id returning * into state;
    return jsonb_build_object('lease',state.lease,'users',to_jsonb(users));
  elsif p_action = 'complete' then
    if p_report is null or jsonb_typeof(p_report) <> 'object' or length(p_report::text) > 1000 or exists(
      select 1 from jsonb_object_keys(p_report) x where x not in ('mode','accounts','candidates','deleted','errors')) then raise invalid_parameter_value; end if;
    if not (p_report ?& array['mode','accounts','candidates','deleted','errors'])
      or coalesce(p_report->>'mode','') not in ('audit','apply')
      or exists(select 1 from jsonb_each(p_report) x where x.key <> 'mode' and
        (jsonb_typeof(x.value) <> 'number' or x.value::text !~ '^[0-9]{1,7}$'))
      or (p_report->>'accounts')::integer > 5 or (p_report->>'errors')::integer > 5
      or (p_report->>'deleted')::integer > 500 then raise invalid_parameter_value; end if;
    update app_private.retention_schedule set report = p_report, completed_at = now(), lease = null where id and lease = p_lease;
    return jsonb_build_object('acknowledged',found);
  end if;
  raise invalid_parameter_value;
end $$;
revoke all on function public.retention_schedule_operation(text,uuid,jsonb) from public, anon, authenticated;
grant execute on function public.retention_schedule_operation(text,uuid,jsonb) to service_role;
