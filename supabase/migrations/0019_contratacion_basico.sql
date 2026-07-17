-- 0019 - Contratacion del Plan Basico reconocida (renumerada desde la
-- migracion duplicada 0017 para mantener una historia lineal en Supabase).

begin;

alter table public.addon_requests
  drop constraint if exists addon_requests_tipo_check;

alter table public.addon_requests
  add constraint addon_requests_tipo_check
  check (tipo in (
    'tokens_limpieza',
    'upgrade_basico',
    'upgrade_analista',
    'upgrade_gold',
    'otro'
  ));

-- El historial no se reclasifica automáticamente: una migración de esquema no
-- debe inferir ni cambiar decisiones empresariales ya registradas.

commit;
