-- 0021 - Estado global multihoja y alcance analitico confirmado (Fase 17).
-- Aditiva y compatible con los snapshots v3 almacenados por 0020.

begin;

alter table public.dataset_restore_states
  add column if not exists selected_sheets jsonb not null default '[]'::jsonb,
  add column if not exists sheet_errors jsonb not null default '{}'::jsonb,
  add column if not exists analysis_scope jsonb not null default '{}'::jsonb;

alter table public.dataset_restore_states
  drop constraint if exists dataset_restore_states_selected_sheets_check,
  add constraint dataset_restore_states_selected_sheets_check
    check (jsonb_typeof(selected_sheets) = 'array'),
  drop constraint if exists dataset_restore_states_sheet_errors_check,
  add constraint dataset_restore_states_sheet_errors_check
    check (jsonb_typeof(sheet_errors) = 'object'),
  drop constraint if exists dataset_restore_states_analysis_scope_check,
  add constraint dataset_restore_states_analysis_scope_check
    check (jsonb_typeof(analysis_scope) = 'object');

create or replace function public.store_restore_snapshot_guarded_v2(
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
  p_engine_version text,
  p_selected_sheets jsonb,
  p_sheet_errors jsonb,
  p_analysis_scope jsonb
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
     or jsonb_typeof(p_selected_sheets) <> 'array'
     or jsonb_typeof(p_sheet_errors) <> 'object'
     or jsonb_typeof(p_analysis_scope) <> 'object'
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
    excluded_sheets, combine_sheets, selected_sheets, sheet_errors,
    analysis_scope, source_sha256, engine_version, updated_at
  ) values (
    p_dataset_id, p_user_id, p_revision, p_active_sheet, p_available_sheets,
    p_excluded_sheets, p_combine_sheets, p_selected_sheets, p_sheet_errors,
    p_analysis_scope, p_source_sha256, p_engine_version, now()
  )
  on conflict (dataset_id) do update set
    user_id = excluded.user_id,
    revision = excluded.revision,
    active_sheet = excluded.active_sheet,
    available_sheets = excluded.available_sheets,
    excluded_sheets = excluded.excluded_sheets,
    combine_sheets = excluded.combine_sheets,
    selected_sheets = excluded.selected_sheets,
    sheet_errors = excluded.sheet_errors,
    analysis_scope = excluded.analysis_scope,
    source_sha256 = excluded.source_sha256,
    engine_version = excluded.engine_version,
    updated_at = now()
  where excluded.revision > dataset_restore_states.revision;

  if not exists (
    select 1 from public.dataset_restore_states s
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

revoke all on function public.store_restore_snapshot_guarded_v2(
  uuid, uuid, text, jsonb, bigint, text, text, text, text, text,
  jsonb, jsonb, boolean, text, jsonb, jsonb, jsonb
) from public, anon, authenticated;
grant execute on function public.store_restore_snapshot_guarded_v2(
  uuid, uuid, text, jsonb, bigint, text, text, text, text, text,
  jsonb, jsonb, boolean, text, jsonb, jsonb, jsonb
) to service_role;

commit;
