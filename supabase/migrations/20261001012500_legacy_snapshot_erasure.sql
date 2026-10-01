begin;

-- A manual pre-0022 snapshot exists only on the original production project.
-- Keep this migration portable: disposable/greenfield databases do not have it.
create function public.purge_legacy_account_snapshot(p_user_id uuid) returns integer
language plpgsql security definer set search_path = '' as $$
declare deleted_rows integer := 0;
declare affected integer;
declare table_name text;
begin
  if to_regclass('backup_pre_0022_20260731_2305.datasets') is null then
    return 0;
  end if;

  execute 'delete from backup_pre_0022_20260731_2305.dataset_columns c '
          'where c.dataset_id in (select d.id from backup_pre_0022_20260731_2305.datasets d where d.user_id=$1)'
    using p_user_id;
  get diagnostics affected = row_count; deleted_rows := deleted_rows + affected;

  foreach table_name in array array[
    'account_trials','activity_log','addon_requests','ai_usage','analyses',
    'billing_identities','cleaning_jobs','dataset_deletion_jobs',
    'dataset_restore_states','dataset_sheet_snapshots','datasets','plan_addons',
    'support_requests'
  ] loop
    execute format('delete from backup_pre_0022_20260731_2305.%I where user_id=$1', table_name)
      using p_user_id;
    get diagnostics affected = row_count; deleted_rows := deleted_rows + affected;
  end loop;

  execute 'delete from backup_pre_0022_20260731_2305.admin_audit where target_user_id=$1'
    using p_user_id;
  get diagnostics affected = row_count; deleted_rows := deleted_rows + affected;
  execute 'delete from backup_pre_0022_20260731_2305.profiles where id=$1'
    using p_user_id;
  get diagnostics affected = row_count; deleted_rows := deleted_rows + affected;
  return deleted_rows;
end;
$$;
revoke all on function public.purge_legacy_account_snapshot(uuid) from public, anon, authenticated;
grant execute on function public.purge_legacy_account_snapshot(uuid) to service_role;

commit;
