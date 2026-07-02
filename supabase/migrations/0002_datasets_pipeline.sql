-- ─────────────────────────────────────────────────────────────────
-- Migración 0002 — Pipeline de datos (Fase 1)
-- Datasets cargados, mapeo de columnas, trabajos de limpieza e historial.
-- Ejecutar después de 0001_profiles.sql.
-- ─────────────────────────────────────────────────────────────────

-- ── Archivos/datasets cargados por el usuario ──
create table public.datasets (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users (id) on delete cascade,
  name         text not null,
  source       text not null default 'excel_csv',
  storage_path text,
  rows         integer,
  columns      integer,
  status       text not null default 'cargado'
               constraint datasets_status_check
               check (status in ('cargado', 'estandarizado', 'limpio', 'error')),
  quality      numeric(5, 1),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

comment on table public.datasets is
  'Archivos cargados: metadata, ruta en Storage, estado del pipeline y calidad %.';

-- ── Mapeo de columnas detectadas al esquema normalizado ──
create table public.dataset_columns (
  id              uuid primary key default gen_random_uuid(),
  dataset_id      uuid not null references public.datasets (id) on delete cascade,
  original_name   text not null,
  normalized_name text not null,
  detected_type   text not null default 'texto'
                  constraint dataset_columns_type_check
                  check (detected_type in ('fecha', 'numero', 'texto')),
  mapped_role     text
                  constraint dataset_columns_role_check
                  check (mapped_role in ('fecha', 'cliente', 'producto', 'categoria',
                                         'monto', 'cantidad', 'canal', 'sucursal',
                                         'vendedor')),
  created_at      timestamptz not null default now()
);

-- ── Trabajos de limpieza: reglas, problemas y antes/después ──
create table public.cleaning_jobs (
  id                uuid primary key default gen_random_uuid(),
  dataset_id        uuid not null references public.datasets (id) on delete cascade,
  user_id           uuid not null references auth.users (id) on delete cascade,
  rules             jsonb not null default '{}'::jsonb,
  problems_detected jsonb not null default '{}'::jsonb,
  problems_fixed    jsonb not null default '{}'::jsonb,
  rows_before       integer,
  rows_after        integer,
  quality_before    numeric(5, 1),
  quality_after     numeric(5, 1),
  status            text not null default 'completado'
                    constraint cleaning_jobs_status_check
                    check (status in ('completado', 'error')),
  created_at        timestamptz not null default now()
);

-- ── Historial básico de actividad (módulo Historial) ──
create table public.activity_log (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users (id) on delete cascade,
  dataset_id    uuid references public.datasets (id) on delete set null,
  activity_type text not null
                constraint activity_log_type_check
                check (activity_type in ('carga', 'estandarizacion', 'limpieza',
                                         'analisis', 'chat', 'recomendacion')),
  description   text not null,
  metadata      jsonb not null default '{}'::jsonb,
  created_at    timestamptz not null default now()
);

create index datasets_user_idx on public.datasets (user_id, created_at desc);
create index dataset_columns_dataset_idx on public.dataset_columns (dataset_id);
create index cleaning_jobs_user_idx on public.cleaning_jobs (user_id, created_at desc);
create index activity_log_user_idx on public.activity_log (user_id, created_at desc);

-- ── updated_at automático (reutiliza set_updated_at de 0001) ──
create trigger datasets_set_updated_at
  before update on public.datasets
  for each row execute procedure public.set_updated_at();

-- ── Row Level Security: cada usuario solo ve y toca lo suyo ──
alter table public.datasets enable row level security;
alter table public.dataset_columns enable row level security;
alter table public.cleaning_jobs enable row level security;
alter table public.activity_log enable row level security;

create policy "datasets_select_own" on public.datasets
  for select using (auth.uid() = user_id);
create policy "datasets_insert_own" on public.datasets
  for insert with check (auth.uid() = user_id);
create policy "datasets_update_own" on public.datasets
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "datasets_delete_own" on public.datasets
  for delete using (auth.uid() = user_id);

create policy "dataset_columns_select_own" on public.dataset_columns
  for select using (exists (
    select 1 from public.datasets d
    where d.id = dataset_id and d.user_id = auth.uid()
  ));
create policy "dataset_columns_insert_own" on public.dataset_columns
  for insert with check (exists (
    select 1 from public.datasets d
    where d.id = dataset_id and d.user_id = auth.uid()
  ));

create policy "cleaning_jobs_select_own" on public.cleaning_jobs
  for select using (auth.uid() = user_id);
create policy "cleaning_jobs_insert_own" on public.cleaning_jobs
  for insert with check (auth.uid() = user_id);

create policy "activity_log_select_own" on public.activity_log
  for select using (auth.uid() = user_id);
create policy "activity_log_insert_own" on public.activity_log
  for insert with check (auth.uid() = user_id);

-- ── Storage: bucket privado para los archivos del pipeline ──
insert into storage.buckets (id, name, public)
values ('datasets', 'datasets', false)
on conflict (id) do nothing;

-- Cada usuario solo puede subir/leer dentro de su carpeta {user_id}/...
create policy "datasets_storage_insert_own" on storage.objects
  for insert with check (
    bucket_id = 'datasets'
    and auth.uid()::text = (storage.foldername(name))[1]
  );
create policy "datasets_storage_select_own" on storage.objects
  for select using (
    bucket_id = 'datasets'
    and auth.uid()::text = (storage.foldername(name))[1]
  );
