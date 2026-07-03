-- ─────────────────────────────────────────────────────────────────
-- Migración 0004 — Análisis guardados (Fase 4: Explorar datos)
-- Guarda la configuración, hallazgos y recomendación de un análisis
-- para retomarlo o compartirlo después. Ejecutar tras 0003.
-- ─────────────────────────────────────────────────────────────────

create table public.analyses (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users (id) on delete cascade,
  dataset_id     uuid references public.datasets (id) on delete set null,
  name           text not null,
  config         jsonb not null default '{}'::jsonb,  -- rango, agrupar_por, metrica
  findings       jsonb not null default '[]'::jsonb,  -- hallazgos al momento de guardar
  recommendation jsonb,                               -- recomendación IA (si se generó)
  created_at     timestamptz not null default now()
);

comment on table public.analyses is
  'Análisis guardados desde Explorar datos: configuración + hallazgos + recomendación.';

create index analyses_user_idx on public.analyses (user_id, created_at desc);

alter table public.analyses enable row level security;

create policy "analyses_select_own" on public.analyses
  for select using (auth.uid() = user_id);
create policy "analyses_insert_own" on public.analyses
  for insert with check (auth.uid() = user_id);
create policy "analyses_delete_own" on public.analyses
  for delete using (auth.uid() = user_id);
