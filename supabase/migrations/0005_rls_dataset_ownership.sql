-- ─────────────────────────────────────────────────────────────────
-- Migración 0005 — RLS estricta sobre dataset_id (Fase 5, seguridad)
-- Las políticas de insert de cleaning_jobs, activity_log y analyses
-- validaban solo user_id: un usuario malicioso podía insertar filas
-- apuntando al dataset_id de otro usuario (si conocía el UUID).
-- Ahora el dataset referenciado también debe pertenecerle.
-- Ejecutar tras 0004.
-- ─────────────────────────────────────────────────────────────────

drop policy if exists "cleaning_jobs_insert_own" on public.cleaning_jobs;
create policy "cleaning_jobs_insert_own" on public.cleaning_jobs
  for insert with check (
    auth.uid() = user_id
    and exists (
      select 1 from public.datasets d
      where d.id = dataset_id and d.user_id = auth.uid()
    )
  );

drop policy if exists "activity_log_insert_own" on public.activity_log;
create policy "activity_log_insert_own" on public.activity_log
  for insert with check (
    auth.uid() = user_id
    and (
      dataset_id is null
      or exists (
        select 1 from public.datasets d
        where d.id = dataset_id and d.user_id = auth.uid()
      )
    )
  );

drop policy if exists "analyses_insert_own" on public.analyses;
create policy "analyses_insert_own" on public.analyses
  for insert with check (
    auth.uid() = user_id
    and (
      dataset_id is null
      or exists (
        select 1 from public.datasets d
        where d.id = dataset_id and d.user_id = auth.uid()
      )
    )
  );
