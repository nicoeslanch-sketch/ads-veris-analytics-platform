-- Migracion 0003 - Campos de contacto en perfiles
-- Agrega pais y telefono al registro sin afectar usuarios existentes.

alter table public.profiles
  add column if not exists country text,
  add column if not exists phone text;

comment on column public.profiles.country is
  'Pais informado por el usuario al registrarse.';

comment on column public.profiles.phone is
  'Numero de telefono informado por el usuario al registrarse.';

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, full_name, company, country, phone)
  values (
    new.id,
    new.raw_user_meta_data ->> 'full_name',
    new.raw_user_meta_data ->> 'company',
    new.raw_user_meta_data ->> 'country',
    new.raw_user_meta_data ->> 'phone'
  );
  return new;
end;
$$;
