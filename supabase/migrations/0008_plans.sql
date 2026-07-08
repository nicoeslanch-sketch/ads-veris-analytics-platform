-- ─────────────────────────────────────────────────────────────────
-- Migración 0008 — Modelo de tres planes (Fase 7)
-- Ejecutar tras 0007, ANTES de desplegar el backend de la Fase 7.
--
-- Historia: hasta ahora la base guardaba `gold` para el plan que la UI
-- mostraba como "Analista". Desde la Fase 7 los planes son:
--   basico → analista → gold (en construcción: SQL + comunidad)
-- Esta migración renombra los `gold` existentes a `analista`; `gold`
-- queda reservado para el tercer plan.
-- ─────────────────────────────────────────────────────────────────

-- 1) Ampliar el enum de plan y migrar las filas existentes.
alter table public.profiles
  drop constraint if exists profiles_plan_check;

update public.profiles set plan = 'analista' where plan = 'gold';

alter table public.profiles
  add constraint profiles_plan_check
  check (plan in ('basico', 'analista', 'gold'));

comment on column public.profiles.plan is
  'Plan comercial: basico | analista | gold (Fase 7). Gold = en construcción (SQL + comunidad).';

-- 2) Administradores: pueden otorgar créditos addon a mano
--    (POST /admin/grant-credits). Se marca por SQL en Supabase:
--    update public.profiles set is_admin = true where id = '<uuid>';
alter table public.profiles
  add column if not exists is_admin boolean not null default false;

comment on column public.profiles.is_admin is
  'Permite usar los endpoints /admin/* del backend (otorgar tokens addon).';

-- 3) Fix: el mapeo automático detecta el rol `costo` desde la Fase 2, pero el
--    check de dataset_columns no lo permitía y el guardado del mapeo fallaba
--    en silencio para esa columna.
alter table public.dataset_columns
  drop constraint if exists dataset_columns_role_check;

alter table public.dataset_columns
  add constraint dataset_columns_role_check
  check (mapped_role in ('fecha', 'cliente', 'producto', 'categoria',
                         'monto', 'costo', 'cantidad', 'canal', 'sucursal',
                         'vendedor'));

-- 4) El usuario puede corregir el rol de sus columnas desde la UI (§5.10).
--    RLS: solo sobre columnas de datasets propios (mismo patrón que 0005).
drop policy if exists "dataset_columns_update_own" on public.dataset_columns;
create policy "dataset_columns_update_own"
  on public.dataset_columns for update
  using (
    exists (
      select 1 from public.datasets d
      where d.id = dataset_id and d.user_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from public.datasets d
      where d.id = dataset_id and d.user_id = auth.uid()
    )
  );

grant update (mapped_role) on table public.dataset_columns to authenticated;
