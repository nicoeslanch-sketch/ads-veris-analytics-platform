-- Fase 12, Bloque 6A: eliminación recuperable de datasets.
-- Ejecutar después de 0012_cleaning_job_options.sql.

create table if not exists public.dataset_deletion_jobs (
  id             uuid primary key default gen_random_uuid(),
  -- Sin FK a datasets a propósito: el trabajo debe sobrevivir a la eliminación
  -- para confirmar el resultado y permitir reintentos idempotentes.
  dataset_id     uuid not null,
  user_id        uuid not null references auth.users (id) on delete cascade,
  dataset_name   text not null,
  storage_path   text,
  status         text not null default 'pending'
                 constraint dataset_deletion_jobs_status_check
                 check (status in (
                   'pending', 'deleting_storage', 'deleting_database',
                   'completed', 'failed'
                 )),
  failed_stage   text
                 constraint dataset_deletion_jobs_failed_stage_check
                 check (failed_stage is null or failed_stage in (
                   'deleting_storage', 'deleting_database'
                 )),
  last_error     text,
  attempt_count  integer not null default 0 check (attempt_count >= 0),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  completed_at   timestamptz,
  unique (user_id, dataset_id)
);

comment on table public.dataset_deletion_jobs is
  'Saga durable para borrar un objeto de Storage y su dataset sin dejar huérfanos.';

create index if not exists dataset_deletion_jobs_user_idx
  on public.dataset_deletion_jobs (user_id, created_at desc);

drop trigger if exists dataset_deletion_jobs_set_updated_at
  on public.dataset_deletion_jobs;
create trigger dataset_deletion_jobs_set_updated_at
  before update on public.dataset_deletion_jobs
  for each row execute procedure public.set_updated_at();

alter table public.dataset_deletion_jobs enable row level security;

drop policy if exists "dataset_deletion_jobs_select_own"
  on public.dataset_deletion_jobs;
create policy "dataset_deletion_jobs_select_own"
  on public.dataset_deletion_jobs
  for select using (auth.uid() = user_id);

grant select on table public.dataset_deletion_jobs to authenticated;
grant all privileges on table public.dataset_deletion_jobs to service_role;

-- La actividad de eliminación queda visible en el historial retenido.
alter table public.activity_log
  drop constraint if exists activity_log_type_check;
alter table public.activity_log
  add constraint activity_log_type_check
  check (activity_type in (
    'carga', 'estandarizacion', 'limpieza', 'analisis', 'chat',
    'recomendacion', 'eliminacion'
  ));

-- Fase PostgreSQL atómica de la saga. Storage se elimina antes desde la API;
-- aquí el log, las cascadas y el estado completed se confirman juntos.
create or replace function public.finalize_dataset_deletion(
  p_job_id uuid,
  p_user_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  job public.dataset_deletion_jobs%rowtype;
begin
  select * into job
  from public.dataset_deletion_jobs
  where id = p_job_id and user_id = p_user_id
  for update;

  if not found then
    raise exception 'dataset deletion job not found';
  end if;

  if job.status = 'completed' then
    return jsonb_build_object('status', 'completed', 'dataset_id', job.dataset_id);
  end if;

  if not (
    job.status = 'deleting_database'
    or (job.status = 'failed' and job.failed_stage = 'deleting_database')
  ) then
    raise exception 'dataset deletion job is not ready for database finalization';
  end if;

  insert into public.activity_log (
    user_id, dataset_id, activity_type, description, metadata
  )
  select
    job.user_id,
    null,
    'eliminacion',
    'Archivo eliminado por el usuario: ' || job.dataset_name,
    jsonb_build_object(
      'deletion_job_id', job.id::text,
      'dataset_id', job.dataset_id::text,
      'dataset_name', job.dataset_name
    )
  where not exists (
    select 1
    from public.activity_log log
    where log.user_id = job.user_id
      and log.metadata ->> 'deletion_job_id' = job.id::text
  );

  -- dataset_columns y cleaning_jobs: ON DELETE CASCADE.
  -- activity_log y analyses: ON DELETE SET NULL.
  delete from public.datasets
  where id = job.dataset_id and user_id = job.user_id;

  update public.dataset_deletion_jobs
  set status = 'completed',
      failed_stage = null,
      last_error = null,
      completed_at = now()
  where id = job.id;

  return jsonb_build_object('status', 'completed', 'dataset_id', job.dataset_id);
end;
$$;

revoke all on function public.finalize_dataset_deletion(uuid, uuid)
  from public, anon, authenticated;
grant execute on function public.finalize_dataset_deletion(uuid, uuid)
  to service_role;
