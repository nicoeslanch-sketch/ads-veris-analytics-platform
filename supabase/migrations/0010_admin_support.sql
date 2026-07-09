-- ─────────────────────────────────────────────────────────────────
-- Migración 0010 — Panel de administración y soporte (Fase 8)
-- Ejecutar tras 0009, ANTES de desplegar el backend de la Fase 8.
--
-- - Marca servicios@adsveris.com como cuenta administradora (acceso a
--   todo sin depender de planes + página "Administrar cuentas").
-- - support_requests: lo que genera el botón "¿Necesitas ayuda?" del
--   sidebar; llega a la bandeja del administrador.
-- - admin_audit: TODO cambio manual (plan, créditos, soporte atendido)
--   queda registrado con quién lo hizo y cuándo. Auditable por diseño.
-- ─────────────────────────────────────────────────────────────────

-- 1) Cuenta administradora. Si la cuenta aún no existe al correr esta
--    migración, vuelve a ejecutar este UPDATE cuando se registre.
update public.profiles
set is_admin = true
where id in (
  select id from auth.users where lower(email) = 'servicios@adsveris.com'
);

-- 2) Solicitudes de ayuda / soporte (botón "¿Necesitas ayuda?").
create table public.support_requests (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users (id) on delete cascade,
  mensaje     text not null,
  pagina      text,             -- desde qué página se pidió ayuda (contexto)
  status      text not null default 'pendiente'
              constraint support_requests_status_check
              check (status in ('pendiente', 'atendida')),
  respuesta   text,             -- respuesta del administrador (visible para el usuario)
  created_at  timestamptz not null default now(),
  attended_at timestamptz
);

comment on table public.support_requests is
  'Solicitudes de ayuda del botón del sidebar. El administrador las atiende desde Administrar cuentas.';

create index support_requests_status_idx on public.support_requests (status, created_at desc);
create index support_requests_user_idx on public.support_requests (user_id, created_at desc);

alter table public.support_requests enable row level security;

-- El usuario ve sus propias solicitudes (y la respuesta del admin);
-- escribe SOLO el backend (service_role salta RLS).
create policy "support_requests_select_own" on public.support_requests
  for select using (auth.uid() = user_id);

grant select on table public.support_requests to authenticated;
grant all privileges on table public.support_requests to service_role;

-- 3) Auditoría de acciones administrativas (solo backend, sin políticas:
--    únicamente service_role puede leer/escribir).
create table public.admin_audit (
  id             uuid primary key default gen_random_uuid(),
  admin_id       uuid not null,
  target_user_id uuid,
  action         text not null,   -- 'set_plan' | 'grant_credits' | 'support_attended' | 'addon_attended'
  detail         jsonb,
  created_at     timestamptz not null default now()
);

comment on table public.admin_audit is
  'Registro de acciones manuales del administrador (cambios de plan, créditos, soporte).';

create index admin_audit_created_idx on public.admin_audit (created_at desc);

alter table public.admin_audit enable row level security;

grant all privileges on table public.admin_audit to service_role;
