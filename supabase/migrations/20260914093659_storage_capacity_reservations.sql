-- Phase 1: server-only accounting. Direct upload policy is closed separately
-- after both API and frontend have switched to the managed upload endpoint.
create schema if not exists app_private;
revoke all on schema app_private from public, anon, authenticated;
grant usage on schema app_private to service_role;

create table app_private.storage_budget (
  id boolean primary key default true check (id),
  project_bytes bigint not null check (project_bytes > 0)
);
insert into app_private.storage_budget values (true, 786432000);
create table app_private.storage_reservations (
  path text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  bytes bigint not null check (bytes > 0 and bytes <= 536870912),
  kind text not null check (kind in ('source', 'artifact')),
  created_at timestamptz not null default now()
);
create index storage_reservations_user_idx on app_private.storage_reservations(user_id);
alter table app_private.storage_budget enable row level security;
alter table app_private.storage_reservations enable row level security;
revoke all on app_private.storage_budget, app_private.storage_reservations from public, anon, authenticated;
grant select, update on app_private.storage_budget to service_role;
grant select, insert, delete on app_private.storage_reservations to service_role;

create function public.storage_capacity(p_user_id uuid) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare
  v_plan text; v_admin boolean; v_limit bigint; v_files int;
  v_used bigint; v_global bigint; v_pending bigint; v_global_pending bigint;
  v_count int; v_pending_count int; v_project_limit bigint;
begin
  select plan, is_admin into v_plan, v_admin from public.profiles where id = p_user_id;
  if not found then raise exception 'Unknown account'; end if;
  v_limit := case when v_admin or v_plan = 'gold' then 524288000 when v_plan = 'analista' then 262144000 else 104857600 end;
  v_files := case when v_admin or v_plan = 'gold' then 50 when v_plan = 'analista' then 25 else 10 end;
  select coalesce(sum(coalesce((metadata->>'size')::bigint, 67108864)),0),
         coalesce(sum(coalesce((metadata->>'size')::bigint, 67108864)) filter(where split_part(name,'/',1) = p_user_id::text),0),
         count(*) filter(where split_part(name,'/',1) = p_user_id::text and array_length(string_to_array(name,'/'),1) = 2)
    into v_global, v_used, v_count from storage.objects where bucket_id = 'datasets';
  select coalesce(sum(greatest(r.bytes - coalesce((o.metadata->>'size')::bigint,0),0)),0),
         coalesce(sum(greatest(r.bytes - coalesce((o.metadata->>'size')::bigint,0),0)) filter(where r.user_id = p_user_id),0),
         count(*) filter(where r.user_id = p_user_id and r.kind = 'source' and o.id is null)
    into v_global_pending, v_pending, v_pending_count
    from app_private.storage_reservations r left join storage.objects o on o.bucket_id = 'datasets' and o.name = r.path;
  select project_bytes into v_project_limit from app_private.storage_budget where id;
  return jsonb_build_object('used_bytes',v_used,'reserved_bytes',v_pending,'limit_bytes',v_limit,
    'files',v_count,'reserved_files',v_pending_count,'limit_files',v_files,
    'project_used_bytes',v_global,'project_reserved_bytes',v_global_pending,'project_limit_bytes',v_project_limit);
end $$;
revoke all on function public.storage_capacity(uuid) from public, anon, authenticated;
grant execute on function public.storage_capacity(uuid) to service_role;

create function public.reserve_storage_capacity(p_user_id uuid, p_path text, p_bytes bigint, p_kind text)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_usage jsonb; v_old bigint; v_delta bigint; v_exists boolean;
begin
  if p_path is null or split_part(p_path,'/',1) <> p_user_id::text or length(p_path) > 1024
     or p_path ~ '(^|/)\.\.?(/|$)' or p_path like '%\%' or p_path like '%//%'
     or p_bytes is null or p_bytes <= 0 or p_bytes > 536870912
     or p_kind is null or p_kind not in ('source','artifact') then
    raise exception 'Invalid storage reservation';
  end if;
  if p_kind = 'source' and (p_bytes > 15728640 or array_length(string_to_array(p_path,'/'),1) <> 2) then
    raise exception 'Invalid source size or path';
  end if;
  -- One short database lock coordinates all API instances and worker processes.
  perform id from app_private.storage_budget where id for update;
  if exists(select 1 from app_private.storage_reservations where path = p_path) then
    return jsonb_build_object('ok',false,'code','STORAGE_WRITE_PENDING','detail','Ya hay una escritura pendiente para este archivo.');
  end if;
  v_usage := public.storage_capacity(p_user_id);
  select coalesce((metadata->>'size')::bigint,67108864) into v_old from storage.objects where bucket_id = 'datasets' and name = p_path;
  v_exists := found;
  if p_kind = 'source' and v_exists then
    return jsonb_build_object('ok',false,'code','STORAGE_SOURCE_EXISTS','detail','El archivo de origen ya existe; no se sobrescribe.');
  end if;
  v_delta := greatest(p_bytes - coalesce(v_old,0),0);
  if (v_usage->>'used_bytes')::bigint + (v_usage->>'reserved_bytes')::bigint + v_delta > (v_usage->>'limit_bytes')::bigint
     or (p_kind = 'source' and (v_usage->>'files')::int + (v_usage->>'reserved_files')::int >= (v_usage->>'limit_files')::int) then
    return jsonb_build_object('ok',false,'code','STORAGE_QUOTA_EXCEEDED','detail','Alcanzaste la cuota de almacenamiento. Elimina archivos que ya no necesites desde Historial antes de guardar otro.');
  end if;
  if (v_usage->>'project_used_bytes')::bigint + (v_usage->>'project_reserved_bytes')::bigint + v_delta > (v_usage->>'project_limit_bytes')::bigint then
    return jsonb_build_object('ok',false,'code','STORAGE_PROJECT_FULL','detail','El almacenamiento de la plataforma esta temporalmente lleno. Tus archivos existentes siguen disponibles. Contacta a soporte.');
  end if;
  insert into app_private.storage_reservations(path,user_id,bytes,kind) values(p_path,p_user_id,p_bytes,p_kind);
  return jsonb_build_object('ok',true);
end $$;
revoke all on function public.reserve_storage_capacity(uuid,text,bigint,text) from public, anon, authenticated;
grant execute on function public.reserve_storage_capacity(uuid,text,bigint,text) to service_role;

create function public.settle_storage_capacity(p_path text, p_written boolean) returns boolean
language plpgsql security invoker set search_path = '' as $$
begin
  perform id from app_private.storage_budget where id for update;
  if p_written and not exists(select 1 from app_private.storage_reservations r join storage.objects o
      on o.bucket_id = 'datasets' and o.name = r.path where r.path = p_path and (o.metadata->>'size')::bigint = r.bytes) then
    return false;
  end if;
  delete from app_private.storage_reservations where path = p_path;
  return true;
end $$;
revoke all on function public.settle_storage_capacity(text,boolean) from public, anon, authenticated;
grant execute on function public.settle_storage_capacity(text,boolean) to service_role;
-- Uncertain writes never expire automatically: releasing their reservation
-- before confirming the remote outcome could oversubscribe the budget.
