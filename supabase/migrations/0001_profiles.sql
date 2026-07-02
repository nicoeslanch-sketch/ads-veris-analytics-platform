-- ─────────────────────────────────────────────────────────────────
-- Migración 0001 — Perfiles de usuario (Fase 0)
-- Ejecutar en Supabase: Dashboard → SQL Editor, o `supabase db push`.
-- Las tablas del pipeline (datasets, cleaning_jobs, etc.) llegan en Fase 1.
-- ─────────────────────────────────────────────────────────────────

create table public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  full_name   text,
  company     text,
  rut         text,
  plan        text        not null default 'basico'
              constraint profiles_plan_check check (plan in ('basico', 'gold')),
  preferences jsonb       not null default '{
    "currency": "CLP",
    "date_format": "DD/MM/YYYY",
    "decimal_separator": ",",
    "rounding": 0,
    "timezone": "America/Santiago"
  }'::jsonb,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

comment on table public.profiles is
  'Perfil de cada usuario: empresa, RUT, plan (basico|gold) y preferencias de datos (es-CL).';

-- ── Row Level Security: cada usuario solo ve y edita su propio perfil ──
alter table public.profiles enable row level security;

create policy "profiles_select_own"
  on public.profiles for select
  using (auth.uid() = id);

create policy "profiles_update_own"
  on public.profiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- El insert lo hace el trigger (security definer); no se permite insert directo.

-- ── Trigger: crear el perfil automáticamente al registrarse ──
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, full_name, company)
  values (
    new.id,
    new.raw_user_meta_data ->> 'full_name',
    new.raw_user_meta_data ->> 'company'
  );
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ── updated_at automático ──
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute procedure public.set_updated_at();
