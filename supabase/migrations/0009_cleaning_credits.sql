-- ─────────────────────────────────────────────────────────────────
-- Migración 0009 — Créditos de limpieza dirigida y solicitudes (Fase 7)
-- Ejecutar tras 0008.
--
-- - ai_usage acepta kind = 'cleaning': cada intento de limpieza dirigida
--   queda registrado ahí (el backend cuenta por kind, así los intentos de
--   limpieza NO consumen el cupo de insights y viceversa).
-- - plan_addons es un LEDGER: filas positivas = tokens otorgados a mano
--   (admin), filas negativas = consumos del sistema al exceder la base
--   mensual. El saldo del usuario es la suma. Auditable por diseño.
-- - addon_requests guarda lo que genera el botón "Solicitar" de la página
--   Planes; ADS Veris contacta al usuario y otorga los tokens a mano.
-- ─────────────────────────────────────────────────────────────────

-- 1) Nuevo tipo de consumo en ai_usage.
alter table public.ai_usage
  drop constraint if exists ai_usage_kind_check;

alter table public.ai_usage
  add constraint ai_usage_kind_check
  check (kind in ('summary', 'chat', 'recommendation', 'cleaning'));

-- 2) Ledger de créditos addon de limpieza dirigida.
create table public.plan_addons (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade,
  credits    integer not null,          -- positivo = otorgado, negativo = consumido
  granted_by text,                      -- uuid del admin o 'sistema'
  note       text,
  created_at timestamptz not null default now()
);

comment on table public.plan_addons is
  'Ledger de tokens de limpieza dirigida IA: otorgamientos (admin) y consumos (sistema). Saldo = sum(credits).';

create index plan_addons_user_idx on public.plan_addons (user_id, created_at desc);

alter table public.plan_addons enable row level security;

-- El usuario ve su propio ledger; escribe SOLO el backend (service_role salta RLS).
create policy "plan_addons_select_own" on public.plan_addons
  for select using (auth.uid() = user_id);

-- 3) Solicitudes de tokens / upgrade desde la página Planes.
create table public.addon_requests (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade,
  tipo       text not null default 'tokens_limpieza'
             constraint addon_requests_tipo_check
             check (tipo in ('tokens_limpieza', 'upgrade_analista', 'upgrade_gold', 'otro')),
  mensaje    text,
  status     text not null default 'pendiente'
             constraint addon_requests_status_check
             check (status in ('pendiente', 'atendida')),
  created_at timestamptz not null default now()
);

comment on table public.addon_requests is
  'Solicitudes de tokens addon o upgrade de plan. ADS Veris las atiende a mano (status pendiente|atendida).';

create index addon_requests_status_idx on public.addon_requests (status, created_at desc);

alter table public.addon_requests enable row level security;

create policy "addon_requests_select_own" on public.addon_requests
  for select using (auth.uid() = user_id);

-- 4) Grants PostgREST (mismo patrón que la migración 0007).
grant select on table public.plan_addons to authenticated;
grant select on table public.addon_requests to authenticated;

grant all privileges on table public.plan_addons to service_role;
grant all privileges on table public.addon_requests to service_role;
