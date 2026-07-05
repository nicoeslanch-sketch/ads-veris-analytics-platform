-- Migration 0007 - PostgREST grants for RLS-protected public tables.
--
-- RLS decides which rows each user can access. These grants only let the
-- Supabase API roles attempt the operations allowed by those policies.

grant usage on schema public to authenticated, service_role;

-- User-facing tables accessed from the browser with the authenticated role.
grant select, update on table public.profiles to authenticated;

grant select, insert, update, delete on table public.datasets to authenticated;
grant select, insert on table public.dataset_columns to authenticated;
grant select, insert on table public.cleaning_jobs to authenticated;
grant select, insert on table public.activity_log to authenticated;
grant select, insert, delete on table public.analyses to authenticated;
grant select on table public.ai_usage to authenticated;

-- Backend calls use the service_role key and still need table privileges.
grant all privileges on table public.profiles to service_role;
grant all privileges on table public.datasets to service_role;
grant all privileges on table public.dataset_columns to service_role;
grant all privileges on table public.cleaning_jobs to service_role;
grant all privileges on table public.activity_log to service_role;
grant all privileges on table public.analyses to service_role;
grant all privileges on table public.ai_usage to service_role;
