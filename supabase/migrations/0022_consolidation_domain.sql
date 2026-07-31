-- 0022 - Dominio aislado de consolidación y recodificación.
-- ADITIVA. Este archivo se versiona pero no se aplica automáticamente.

begin;

create table if not exists public.consolidation_projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  status text not null default 'draft' check (status in (
    'draft','validating','valid_with_warnings','blocked','preview_ready',
    'queued','running','partial','certified','failed'
  )),
  config jsonb not null default '{}'::jsonb check (jsonb_typeof(config) = 'object'),
  config_hash text not null check (config_hash ~ '^[0-9a-f]{64}$'),
  engine_version text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.consolidation_project_sources (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.consolidation_projects(id) on delete cascade,
  dataset_id uuid references public.datasets(id) on delete set null,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in (
    'matricula','archivo_b','archivo_c','archivo_d','oferta','historica',
    'codebook_matricula','codebook_b','codebook_c','codebook_d'
  )),
  required boolean not null default true,
  selected_sheet text,
  source_hash text check (source_hash is null or source_hash ~ '^[0-9a-f]{64}$'),
  profile jsonb not null default '{}'::jsonb check (jsonb_typeof(profile) = 'object'),
  status text not null default 'draft' check (status in ('draft','valid','warning','blocked')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(project_id, role)
);

create table if not exists public.consolidation_runs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.consolidation_projects(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  status text not null default 'queued' check (status in (
    'queued','running','partial','certified','valid_with_warnings','blocked','failed'
  )),
  input_hash text check (input_hash is null or input_hash ~ '^[0-9a-f]{64}$'),
  config_hash text not null check (config_hash ~ '^[0-9a-f]{64}$'),
  engine_version text not null,
  idempotency_key text not null check (char_length(idempotency_key) between 16 and 128),
  report jsonb not null default '{}'::jsonb check (jsonb_typeof(report) = 'object'),
  error_code text,
  error_message text,
  reused_run_id uuid references public.consolidation_runs(id) on delete set null,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  unique(user_id, idempotency_key)
);

create table if not exists public.consolidation_artifacts (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.consolidation_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (kind in ('annual','historical','audit','manifest')),
  storage_path text not null,
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  bytes bigint not null check (bytes >= 0),
  created_at timestamptz not null default now(),
  unique(run_id, kind),
  unique(storage_path)
);

create table if not exists public.consolidation_run_events (
  id bigint generated always as identity primary key,
  run_id uuid not null references public.consolidation_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  stage text not null check (char_length(stage) between 1 and 80),
  status text not null check (status in ('started','completed','warning','failed')),
  row_count bigint check (row_count is null or row_count >= 0),
  duration_ms bigint check (duration_ms is null or duration_ms >= 0),
  memory_bytes bigint check (memory_bytes is null or memory_bytes >= 0),
  detail jsonb not null default '{}'::jsonb check (jsonb_typeof(detail) = 'object'),
  created_at timestamptz not null default now()
);

create index if not exists consolidation_projects_user_idx on public.consolidation_projects(user_id, created_at desc);
create index if not exists consolidation_sources_project_idx on public.consolidation_project_sources(project_id, role);
create index if not exists consolidation_sources_dataset_idx on public.consolidation_project_sources(dataset_id);
create index if not exists consolidation_runs_queue_idx on public.consolidation_runs(status, created_at);
create index if not exists consolidation_runs_project_idx on public.consolidation_runs(project_id, created_at desc);
create index if not exists consolidation_runs_hash_idx on public.consolidation_runs(user_id, input_hash, config_hash) where status in ('partial','certified','valid_with_warnings');
create index if not exists consolidation_artifacts_run_idx on public.consolidation_artifacts(run_id);
create index if not exists consolidation_events_run_idx on public.consolidation_run_events(run_id, created_at);

alter table public.consolidation_projects enable row level security;
alter table public.consolidation_project_sources enable row level security;
alter table public.consolidation_runs enable row level security;
alter table public.consolidation_artifacts enable row level security;
alter table public.consolidation_run_events enable row level security;

drop policy if exists consolidation_projects_select_own on public.consolidation_projects;
create policy consolidation_projects_select_own on public.consolidation_projects for select using (auth.uid() = user_id);
drop policy if exists consolidation_sources_select_own on public.consolidation_project_sources;
create policy consolidation_sources_select_own on public.consolidation_project_sources for select using (auth.uid() = user_id);
drop policy if exists consolidation_runs_select_own on public.consolidation_runs;
create policy consolidation_runs_select_own on public.consolidation_runs for select using (auth.uid() = user_id);
drop policy if exists consolidation_artifacts_select_own on public.consolidation_artifacts;
create policy consolidation_artifacts_select_own on public.consolidation_artifacts for select using (auth.uid() = user_id);
drop policy if exists consolidation_events_select_own on public.consolidation_run_events;
create policy consolidation_events_select_own on public.consolidation_run_events for select using (auth.uid() = user_id);

revoke all on public.consolidation_projects, public.consolidation_project_sources,
  public.consolidation_runs, public.consolidation_artifacts, public.consolidation_run_events
  from anon, authenticated;
grant select on public.consolidation_projects, public.consolidation_project_sources,
  public.consolidation_runs, public.consolidation_artifacts, public.consolidation_run_events
  to authenticated;
grant all privileges on public.consolidation_projects, public.consolidation_project_sources,
  public.consolidation_runs, public.consolidation_artifacts, public.consolidation_run_events
  to service_role;
grant usage, select on sequence public.consolidation_run_events_id_seq to service_role;

commit;
