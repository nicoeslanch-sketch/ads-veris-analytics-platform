-- ============================================================================
-- 0017 — Contratación del Plan Básico reconocida  (Fase 15)
-- ============================================================================
-- Ejecutar en Supabase → SQL Editor (después de la 0016).
--
-- El frontend genera solicitudes upgrade_basico / upgrade_analista /
-- upgrade_gold, pero el CHECK de addon_requests.tipo (migración 0009) solo
-- reconocía Analista y Gold: una solicitud de contratar el PLAN BÁSICO se
-- guardaba degradada como 'otro' — el administrador la veía sin saber qué
-- plan pedía el usuario. Este cambio alinea el constraint con la API
-- (routes/plans.py REQUEST_TYPES).
-- ============================================================================

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

-- Reparación opcional de solicitudes históricas degradadas: si un usuario
-- pidió el Plan Básico y quedó como 'otro', el mensaje lo delata.
update public.addon_requests
   set tipo = 'upgrade_basico'
 where tipo = 'otro'
   and mensaje ilike '%contratar el Plan B_sico%';
