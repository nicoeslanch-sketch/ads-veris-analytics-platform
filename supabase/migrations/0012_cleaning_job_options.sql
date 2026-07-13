-- Fase 12, Bloque 1: decisiones de aplicación separadas de las reglas.
-- Ejecutar después de 0011_lock_privileged_columns.sql.

alter table public.cleaning_jobs
  add column if not exists options jsonb not null
  default '{"eliminar_duplicados": false}'::jsonb;

comment on column public.cleaning_jobs.options is
  'Decisiones explícitas del usuario (p. ej. eliminar_duplicados). No mezclar con rules.';
