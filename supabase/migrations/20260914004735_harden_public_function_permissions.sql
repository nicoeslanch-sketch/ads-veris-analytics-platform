-- Trigger entry points are not public RPCs. Existing triggers remain active.
revoke execute on function public.handle_new_user() from public, anon, authenticated;
-- Hosted projects may have this platform-installed event-trigger function;
-- fresh CLI databases do not. Preserve hardening wherever it exists.
do $$
begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
  end if;
end;
$$;

-- These routines reference only built-in functions and trigger NEW records.
alter function public.set_updated_at() set search_path = pg_catalog;
alter function public.normalize_rut(text) set search_path = pg_catalog;
alter function public.rut_dv_valido(text) set search_path = pg_catalog;
alter function public.mask_rut(text) set search_path = pg_catalog;
alter function public.touch_billing_identities() set search_path = pg_catalog;
