-- Migracion 0018 - acceso persistente de la cuenta administradora.
--
-- 0010 marco la cuenta solo si ya existia al ejecutar esa migracion. Esta
-- version es idempotente y tambien protege altas/cambios futuros del perfil:
-- servicios@adsveris.com siempre conserva is_admin=true.

begin;

create or replace function public.enforce_designated_admin()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if exists (
    select 1
    from auth.users as u
    where u.id = new.id
      and lower(u.email) = 'servicios@adsveris.com'
  ) then
    new.is_admin := true;
  end if;
  return new;
end;
$$;

revoke all on function public.enforce_designated_admin() from public;

drop trigger if exists profiles_enforce_designated_admin on public.profiles;
create trigger profiles_enforce_designated_admin
  before insert or update on public.profiles
  for each row execute function public.enforce_designated_admin();

-- Corrige inmediatamente la fila actual. No cambia el plan comercial: el
-- acceso total proviene del rol is_admin y no de fingir una suscripcion Gold.
update public.profiles as p
set is_admin = true
from auth.users as u
where p.id = u.id
  and lower(u.email) = 'servicios@adsveris.com'
  and p.is_admin is distinct from true;

commit;

comment on function public.enforce_designated_admin() is
  'Mantiene el rol administrador de servicios@adsveris.com en profiles.';
