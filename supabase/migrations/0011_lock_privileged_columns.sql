-- ─────────────────────────────────────────────────────────────────
-- Migración 0011 — P0 SEGURIDAD: bloquear plan e is_admin (Fase 10)
-- Ejecutar tras 0010, ANTES de aceptar usuarios externos o pagos.
--
-- Problema que corrige: la 0007 otorgó a `authenticated` UPDATE sobre
-- TODA la tabla profiles, y la 0008 agregó a esa misma tabla `plan` e
-- `is_admin`. Con la política RLS "profiles_update_own", cualquier
-- usuario autenticado podía llamar directo a la REST API de Supabase y
-- ponerse plan='gold' e is_admin=true en su propia fila — escalando a
-- administrador sin conocer la service_role.
--
-- Corrección: permisos POR COLUMNA. El navegador (rol authenticated)
-- solo puede editar los datos de contacto/preferencias de su perfil;
-- `plan` e `is_admin` SOLO los cambia el backend con la service_role
-- (set_user_plan → auditado en admin_audit) o el panel de Supabase.
--
-- Verificación manual tras ejecutar (con el JWT de un usuario normal):
--   PATCH /rest/v1/profiles?id=eq.<su-id>  {"company": "X"}   → 204 OK
--   PATCH /rest/v1/profiles?id=eq.<su-id>  {"plan": "gold"}   → 403/401
--   PATCH /rest/v1/profiles?id=eq.<su-id>  {"is_admin": true} → 403/401
-- ─────────────────────────────────────────────────────────────────

begin;

revoke update on table public.profiles from authenticated;

grant update (full_name, company, country, phone, rut, preferences)
  on table public.profiles
  to authenticated;

commit;

comment on column public.profiles.plan is
  'Plan comercial: basico | analista | gold. SOLO editable por el backend '
  '(service_role, set_user_plan) — jamás por el rol authenticated (0011).';

comment on column public.profiles.is_admin is
  'Cuenta administradora. SOLO editable por service_role o el panel de '
  'Supabase — jamás por el rol authenticated (0011).';
