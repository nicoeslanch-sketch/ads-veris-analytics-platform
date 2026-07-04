-- ─────────────────────────────────────────────────────────────────
-- Migración 0006 — Consumo de IA por usuario (Fase 5, planes/cuotas)
-- Cada llamada a /ai/summary, /ai/chat y /ai/recommendation registra
-- una fila. La API cuenta el mes en curso y aplica el límite del plan
-- (profiles.plan: basico|gold). Escribe SOLO el backend (service_role,
-- que salta RLS); el usuario puede leer su propio consumo.
-- Ejecutar tras 0005.
-- ─────────────────────────────────────────────────────────────────

create table public.ai_usage (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade,
  kind       text not null
             constraint ai_usage_kind_check
             check (kind in ('summary', 'chat', 'recommendation')),
  created_at timestamptz not null default now()
);

comment on table public.ai_usage is
  'Registro de consultas IA por usuario para cuotas mensuales por plan.';

create index ai_usage_user_month_idx on public.ai_usage (user_id, created_at desc);

alter table public.ai_usage enable row level security;

-- Solo lectura del propio consumo; los inserts los hace el backend con service_role.
create policy "ai_usage_select_own" on public.ai_usage
  for select using (auth.uid() = user_id);
