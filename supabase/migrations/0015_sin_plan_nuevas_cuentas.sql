-- Fase 13: las cuentas NUEVAS nacen sin plan.
--
-- Regla de negocio: quien se registra puede navegar la plataforma, pero para
-- subir/procesar archivos debe contratar un plan (la UI lo lleva a Planes).
-- Las cuentas EXISTENTES no se tocan: conservan su plan actual ('basico',
-- 'analista' o 'gold') y siguen funcionando exactamente igual.
--
-- Ejecutar en el SQL Editor de Supabase DESPUÉS de 0014.

-- 1) Permitir el valor 'sin_plan' en el check del plan (0008 lo limitaba a 3).
alter table public.profiles
  drop constraint if exists profiles_plan_check;
alter table public.profiles
  add constraint profiles_plan_check
  check (plan in ('sin_plan', 'basico', 'analista', 'gold'));

-- 2) Las cuentas nuevas nacen sin plan (el trigger handle_new_user no fija
--    plan explícito: usa el DEFAULT de la columna).
alter table public.profiles
  alter column plan set default 'sin_plan';

-- 3) Ninguna fila existente se modifica: quienes ya tienen cuenta conservan
--    su plan. (Verificación opcional):
--    select plan, count(*) from public.profiles group by plan;
