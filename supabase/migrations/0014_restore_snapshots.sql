-- Fase 12c: restauracion rapida y segura del ultimo trabajo.
-- El snapshot contiene solo respuestas publicas del pipeline, con version.

begin;

alter table public.datasets
  add column if not exists restore_snapshot jsonb;

comment on column public.datasets.restore_snapshot is
  'Snapshot versionado del pipeline para restauracion rapida. Solo lo escribe el backend.';

-- Evita que un cliente pueda falsificar indicadores modificando el snapshot.
-- Se conservan exactamente las columnas que el frontend necesita actualizar.
revoke update on table public.datasets from authenticated;
grant update (name, source, storage_path, rows, columns, status, quality)
  on table public.datasets
  to authenticated;

commit;
