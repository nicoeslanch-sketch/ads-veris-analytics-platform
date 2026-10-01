begin;

-- Every foreign key used by deletes or joins needs an index on the referencing
-- side. These are intentionally ordinary indexes: the relevant tables are
-- small today and must remain predictable as customer volume grows.
create index if not exists account_trials_billing_identity_idx on public.account_trials(billing_identity_id);
create index if not exists activity_log_dataset_idx on public.activity_log(dataset_id);
create index if not exists addon_requests_billing_identity_idx on public.addon_requests(billing_identity_id);
create index if not exists addon_requests_user_fk_idx on public.addon_requests(user_id);
create index if not exists analyses_dataset_idx on public.analyses(dataset_id);
create index if not exists cleaning_jobs_dataset_idx on public.cleaning_jobs(dataset_id);
create index if not exists consolidation_artifacts_user_idx on public.consolidation_artifacts(user_id);
create index if not exists consolidation_project_sources_user_idx on public.consolidation_project_sources(user_id);
create index if not exists consolidation_run_events_user_idx on public.consolidation_run_events(user_id);
create index if not exists consolidation_runs_reused_run_idx on public.consolidation_runs(reused_run_id);
create index if not exists dataset_restore_states_user_idx on public.dataset_restore_states(user_id);
create index if not exists support_conversations_closed_by_idx on public.support_conversations(closed_by);
create index if not exists support_messages_sender_idx on public.support_messages(sender_id);

-- Supabase recommends a scalar subquery around auth.uid(): PostgreSQL creates
-- one initPlan per statement instead of invoking the function for every row.
-- Restrict the policies to authenticated explicitly while preserving ownership.
alter policy account_trials_select_own on public.account_trials to authenticated
  using ((select auth.uid()) = user_id);
alter policy activity_log_select_own on public.activity_log to authenticated
  using ((select auth.uid()) = user_id);
alter policy activity_log_insert_own on public.activity_log to authenticated
  with check ((select auth.uid()) = user_id and (dataset_id is null or exists(
    select 1 from public.datasets d where d.id=activity_log.dataset_id and d.user_id=(select auth.uid()))));
alter policy addon_requests_select_own on public.addon_requests to authenticated
  using ((select auth.uid()) = user_id);
alter policy ai_usage_select_own on public.ai_usage to authenticated
  using ((select auth.uid()) = user_id);
alter policy analyses_select_own on public.analyses to authenticated
  using ((select auth.uid()) = user_id);
alter policy analyses_insert_own on public.analyses to authenticated
  with check ((select auth.uid()) = user_id and (dataset_id is null or exists(
    select 1 from public.datasets d where d.id=analyses.dataset_id and d.user_id=(select auth.uid()))));
alter policy analyses_delete_own on public.analyses to authenticated
  using ((select auth.uid()) = user_id);
alter policy billing_identities_select_own on public.billing_identities to authenticated
  using ((select auth.uid()) = user_id);
alter policy cleaning_jobs_select_own on public.cleaning_jobs to authenticated
  using ((select auth.uid()) = user_id);
alter policy cleaning_jobs_insert_own on public.cleaning_jobs to authenticated
  with check ((select auth.uid()) = user_id and exists(
    select 1 from public.datasets d where d.id=cleaning_jobs.dataset_id and d.user_id=(select auth.uid())));
alter policy consolidation_projects_select_own on public.consolidation_projects to authenticated
  using ((select auth.uid()) = user_id);
alter policy consolidation_sources_select_own on public.consolidation_project_sources to authenticated
  using ((select auth.uid()) = user_id);
alter policy consolidation_runs_select_own on public.consolidation_runs to authenticated
  using ((select auth.uid()) = user_id);
alter policy consolidation_artifacts_select_own on public.consolidation_artifacts to authenticated
  using ((select auth.uid()) = user_id);
alter policy consolidation_events_select_own on public.consolidation_run_events to authenticated
  using ((select auth.uid()) = user_id);
alter policy dataset_columns_select_own on public.dataset_columns to authenticated
  using (exists(select 1 from public.datasets d
    where d.id=dataset_columns.dataset_id and d.user_id=(select auth.uid())));
alter policy dataset_columns_insert_own on public.dataset_columns to authenticated
  with check (exists(select 1 from public.datasets d
    where d.id=dataset_columns.dataset_id and d.user_id=(select auth.uid())));
alter policy dataset_columns_update_own on public.dataset_columns to authenticated
  using (exists(select 1 from public.datasets d
    where d.id=dataset_columns.dataset_id and d.user_id=(select auth.uid())))
  with check (exists(select 1 from public.datasets d
    where d.id=dataset_columns.dataset_id and d.user_id=(select auth.uid())));
alter policy dataset_deletion_jobs_select_own on public.dataset_deletion_jobs to authenticated
  using ((select auth.uid()) = user_id);
alter policy dataset_restore_states_select_own on public.dataset_restore_states to authenticated
  using ((select auth.uid()) = user_id and exists(select 1 from public.datasets d
    where d.id=dataset_restore_states.dataset_id and d.user_id=(select auth.uid())));
alter policy dataset_sheet_snapshots_select_own on public.dataset_sheet_snapshots to authenticated
  using ((select auth.uid()) = user_id and exists(select 1 from public.datasets d
    where d.id=dataset_sheet_snapshots.dataset_id and d.user_id=(select auth.uid())));
alter policy datasets_select_own on public.datasets to authenticated
  using ((select auth.uid()) = user_id);
alter policy datasets_insert_own on public.datasets to authenticated
  with check ((select auth.uid()) = user_id);
alter policy datasets_update_own on public.datasets to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
alter policy datasets_delete_own on public.datasets to authenticated
  using ((select auth.uid()) = user_id);
alter policy plan_addons_select_own on public.plan_addons to authenticated
  using ((select auth.uid()) = user_id);
alter policy profiles_select_own on public.profiles to authenticated
  using ((select auth.uid()) = id);
alter policy profiles_update_own on public.profiles to authenticated
  using ((select auth.uid()) = id) with check ((select auth.uid()) = id);
alter policy support_requests_select_own on public.support_requests to authenticated
  using ((select auth.uid()) = user_id);

commit;
