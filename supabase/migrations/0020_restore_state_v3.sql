-- 0020 - Snapshots Fase 16: revision reservada, escritura atomica y estado
-- multihoja en tablas dedicadas (sin limite de 512 KiB en datasets.jsonb).

begin;

create sequence if not exists public.restore_snapshot_revision_seq;
revoke all on sequence public.restore_snapshot_revision_seq from public, anon, authenticated;
grant usage, select on sequence public.restore_snapshot_revision_seq to service_role;

create table if not exists public.dataset_restore_states (
  dataset_id       uuid primary key references public.datasets (id) on delete cascade,
  user_id          uuid not null references auth.users (id) on delete cascade,
  revision         bigint not null check (revision > 0),
  active_sheet     text,
  available_sheets jsonb not null default '[]'::jsonb
                   check (jsonb_typeof(available_sheets) = 'array'),
  excluded_sheets  jsonb not null default '[]'::jsonb
                   check (jsonb_typeof(excluded_sheets) = 'array'),
  combine_sheets   boolean not null default false,
  source_sha256    text not null check (source_sha256 ~ '^[0-9a-f]{64}$'),
  engine_version   text not null,
  updated_at       timestamptz not null default now(),
  unique (dataset_id, user_id)
);

create table if not exists public.dataset_sheet_snapshots (
  dataset_id     uuid not null references public.datasets (id) on delete cascade,
  sheet_key      text not null,
  user_id        uuid not null references auth.users (id) on delete cascade,
  revision       bigint not null check (revision > 0),
  source_sha256  text not null check (source_sha256 ~ '^[0-9a-f]{64}$'),
  rules_hash     text not null,
  mapping_hash   text not null,
  sheet          text,
  engine_version text not null,
  snapshot       jsonb not null check (jsonb_typeof(snapshot) = 'object'),
  updated_at     timestamptz not null default now(),
  primary key (dataset_id, sheet_key)
);

create index if not exists dataset_sheet_snapshots_user_idx
  on public.dataset_sheet_snapshots (user_id, dataset_id);

alter table public.dataset_restore_states enable row level security;
alter table public.dataset_sheet_snapshots enable row level security;

drop policy if exists "dataset_restore_states_select_own" on public.dataset_restore_states;
create policy "dataset_restore_states_select_own"
  on public.dataset_restore_states for select to authenticated
  using (
    auth.uid() = user_id
    and exists (
      select 1 from public.datasets d
      where d.id = dataset_id and d.user_id = auth.uid()
    )
  );

drop policy if exists "dataset_sheet_snapshots_select_own" on public.dataset_sheet_snapshots;
create policy "dataset_sheet_snapshots_select_own"
  on public.dataset_sheet_snapshots for select to authenticated
  using (
    auth.uid() = user_id
    and exists (
      select 1 from public.datasets d
      where d.id = dataset_id and d.user_id = auth.uid()
    )
  );

revoke all on public.dataset_restore_states from anon, authenticated;
revoke all on public.dataset_sheet_snapshots from anon, authenticated;
grant select on public.dataset_restore_states to authenticated;
grant select on public.dataset_sheet_snapshots to authenticated;
grant all on public.dataset_restore_states to service_role;
grant all on public.dataset_sheet_snapshots to service_role;

create or replace function public.reserve_restore_snapshot_revision(
  p_dataset_id uuid,
  p_user_id uuid
) returns bigint
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_revision bigint;
begin
  if not exists (
    select 1 from public.datasets d
    where d.id = p_dataset_id and d.user_id = p_user_id
  ) then
    raise exception 'dataset not found or not owned by user';
  end if;
  v_revision := nextval('public.restore_snapshot_revision_seq');
  return v_revision;
end;
$$;

revoke all on function public.reserve_restore_snapshot_revision(uuid, uuid)
  from public, anon, authenticated;
grant execute on function public.reserve_restore_snapshot_revision(uuid, uuid)
  to service_role;

create or replace function public.store_restore_snapshot_guarded(
  p_dataset_id uuid,
  p_user_id uuid,
  p_sheet_key text,
  p_snapshot jsonb,
  p_revision bigint,
  p_source_sha256 text,
  p_rules_hash text,
  p_mapping_hash text,
  p_sheet text,
  p_active_sheet text,
  p_available_sheets jsonb,
  p_excluded_sheets jsonb,
  p_combine_sheets boolean,
  p_engine_version text
) returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_sheet_rows integer := 0;
begin
  if p_revision <= 0
     or coalesce(p_sheet_key, '') = ''
     or jsonb_typeof(p_snapshot) <> 'object'
     or jsonb_typeof(p_available_sheets) <> 'array'
     or jsonb_typeof(p_excluded_sheets) <> 'array'
     or p_source_sha256 !~ '^[0-9a-f]{64}$'
     or (p_snapshot ->> 'revision')::bigint <> p_revision
     or p_snapshot ->> 'source_sha256' <> p_source_sha256
     or p_snapshot ->> 'rules_hash' <> p_rules_hash
     or p_snapshot ->> 'mapping_hash' <> p_mapping_hash
     or p_snapshot ->> 'engine_version' <> p_engine_version
     or (p_snapshot ->> 'sheet') is distinct from p_sheet then
    raise exception 'invalid restore snapshot metadata';
  end if;

  if not exists (
    select 1 from public.datasets d
    where d.id = p_dataset_id and d.user_id = p_user_id
  ) then
    raise exception 'dataset not found or not owned by user';
  end if;

  insert into public.dataset_restore_states (
    dataset_id, user_id, revision, active_sheet, available_sheets,
    excluded_sheets, combine_sheets, source_sha256, engine_version, updated_at
  ) values (
    p_dataset_id, p_user_id, p_revision, p_active_sheet, p_available_sheets,
    p_excluded_sheets, p_combine_sheets, p_source_sha256, p_engine_version, now()
  )
  on conflict (dataset_id) do update set
    user_id = excluded.user_id,
    revision = excluded.revision,
    active_sheet = excluded.active_sheet,
    available_sheets = excluded.available_sheets,
    excluded_sheets = excluded.excluded_sheets,
    combine_sheets = excluded.combine_sheets,
    source_sha256 = excluded.source_sha256,
    engine_version = excluded.engine_version,
    updated_at = now()
  where excluded.revision > dataset_restore_states.revision;

  -- Si una petición más nueva ya actualizó el estado global, esta tarea quedó
  -- obsoleta. No puede insertar una hoja tardía aunque esa clave aún no exista.
  if not exists (
    select 1
      from public.dataset_restore_states s
     where s.dataset_id = p_dataset_id
       and s.user_id = p_user_id
       and s.revision = p_revision
  ) then
    return false;
  end if;

  insert into public.dataset_sheet_snapshots (
    dataset_id, sheet_key, user_id, revision, source_sha256, rules_hash,
    mapping_hash, sheet, engine_version, snapshot, updated_at
  ) values (
    p_dataset_id, p_sheet_key, p_user_id, p_revision, p_source_sha256,
    p_rules_hash, p_mapping_hash, p_sheet, p_engine_version, p_snapshot, now()
  )
  on conflict (dataset_id, sheet_key) do update set
    user_id = excluded.user_id,
    revision = excluded.revision,
    source_sha256 = excluded.source_sha256,
    rules_hash = excluded.rules_hash,
    mapping_hash = excluded.mapping_hash,
    sheet = excluded.sheet,
    engine_version = excluded.engine_version,
    snapshot = excluded.snapshot,
    updated_at = now()
  where excluded.revision > dataset_sheet_snapshots.revision;

  get diagnostics v_sheet_rows = row_count;
  return v_sheet_rows > 0;
end;
$$;

revoke all on function public.store_restore_snapshot_guarded(
  uuid, uuid, text, jsonb, bigint, text, text, text, text, text,
  jsonb, jsonb, boolean, text
) from public, anon, authenticated;
grant execute on function public.store_restore_snapshot_guarded(
  uuid, uuid, text, jsonb, bigint, text, text, text, text, text,
  jsonb, jsonb, boolean, text
) to service_role;

commit;
