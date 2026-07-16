-- ============================================================================
-- 0016 — Prueba gratuita de 15 días + identidad de facturación (RUT)  (Fase 14)
-- ============================================================================
-- Ejecutar en Supabase → SQL Editor (después de la 0015).
--
-- Qué crea:
--   1. billing_identities — RUT (empresa o responsable) por usuario, reutilizable
--      para contratación/facturación. Protegido con RLS (solo el dueño lo lee;
--      nadie escribe directo: todas las escrituras pasan por la RPC).
--   2. account_trials — una prueba por USUARIO (unique absoluto) y una por RUT
--      normalizado (índice único PARCIAL sobre revoked_at is null: revocar una
--      prueba apropiada libera el RUT para su titular legítimo, pero el usuario
--      revocado no puede reactivar jamás).
--   3. normalize_rut / rut_dv_valido / mask_rut — normalización y módulo 11
--      idénticos a frontend y backend (api/app/rut.py).
--   4. activate_account_trial — RPC ATÓMICA (SECURITY DEFINER, search_path
--      fijo). Solo la service_role puede ejecutarla: así el rate limiting de
--      la API es insoslayable y ningún cliente le pasa un user_id ajeno
--      (auth.uid() tiene prioridad cuando existe).
--   5. can_process_data() — admin OR plan pagado OR prueba vigente. STABLE
--      (depende de now() y de tablas). La usan políticas RESTRICTIVAS nuevas
--      en public.datasets y storage.objects: las políticas permisivas
--      existentes se combinan con OR, por lo que agregar otra permisiva NO
--      cerraría nada — la restricción real exige AS RESTRICTIVE.
--
-- Qué NO hace:
--   - No toca profiles.plan (la prueba mantiene plan 'sin_plan').
--   - No borra archivos al expirar (la retención sigue igual); solo bloquea
--     NUEVO procesamiento (la vigencia se evalúa contra now(): sin cron).
-- ============================================================================

-- ── 1. Normalización y validación de RUT (espejo de api/app/rut.py) ─────────

create or replace function public.normalize_rut(p_raw text)
returns text
language plpgsql
immutable
as $$
declare
  v_compact text;
  v_body text;
  v_dv text;
begin
  if p_raw is null then
    return null;
  end if;
  v_compact := upper(regexp_replace(trim(p_raw), '[.\s\-]', '', 'g'));
  if length(v_compact) < 2 or length(v_compact) > 10 then
    return null;
  end if;
  v_body := left(v_compact, length(v_compact) - 1);
  v_dv := right(v_compact, 1);
  if v_body !~ '^\d+$' or v_dv !~ '^[0-9K]$' then
    return null;
  end if;
  v_body := ltrim(v_body, '0');
  if v_body = '' then
    return null;
  end if;
  return v_body || '-' || v_dv;
end;
$$;

create or replace function public.rut_dv_valido(p_normalized text)
returns boolean
language plpgsql
immutable
as $$
declare
  v_body text;
  v_dv text;
  v_total integer := 0;
  v_factor integer := 2;
  v_rest integer;
  v_expected text;
  i integer;
begin
  if p_normalized is null or p_normalized !~ '^\d{1,9}-[0-9K]$' then
    return false;
  end if;
  v_body := split_part(p_normalized, '-', 1);
  v_dv := split_part(p_normalized, '-', 2);
  for i in reverse length(v_body)..1 loop
    v_total := v_total + (substr(v_body, i, 1))::integer * v_factor;
    v_factor := case when v_factor = 7 then 2 else v_factor + 1 end;
  end loop;
  v_rest := 11 - (v_total % 11);
  v_expected := case v_rest when 11 then '0' when 10 then 'K' else v_rest::text end;
  return v_expected = v_dv;
end;
$$;

create or replace function public.mask_rut(p_normalized text)
returns text
language sql
immutable
as $$
  select case
    when p_normalized !~ '^\d{1,9}-[0-9K]$' then '***'
    else (
      case
        when length(split_part(p_normalized, '-', 1)) > 6
          then left(split_part(p_normalized, '-', 1), length(split_part(p_normalized, '-', 1)) - 6)
        else left(split_part(p_normalized, '-', 1), 1)
      end
    ) || '.***.***-' || split_part(p_normalized, '-', 2)
  end;
$$;

-- ── 2. Tablas ────────────────────────────────────────────────────────────────

create table if not exists public.billing_identities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  rut_type text not null check (rut_type in ('empresa', 'responsable')),
  rut_normalized text not null check (rut_normalized ~ '^\d{1,9}-[0-9K]$'),
  rut_masked text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- Un registro por (usuario, RUT): re-enviar el mismo RUT actualiza el tipo
  -- en vez de duplicar la identidad. La unicidad COMERCIAL por RUT no vive
  -- aquí (dos usuarios de la misma empresa pueden registrar el mismo RUT para
  -- facturación): vive en account_trials, que es donde importa.
  unique (user_id, rut_normalized)
);

create table if not exists public.account_trials (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  billing_identity_id uuid not null references public.billing_identities (id),
  rut_normalized text not null check (rut_normalized ~ '^\d{1,9}-[0-9K]$'),
  started_at timestamptz not null default now(),
  ends_at timestamptz not null,
  revoked_at timestamptz,
  revoked_reason text,
  created_at timestamptz not null default now(),
  -- UNA prueba por usuario, PARA SIEMPRE (revocada o no): quien abusó no
  -- reactiva. La recuperación de la víctima no necesita tocar esta regla —
  -- su cuenta nunca tuvo trial.
  constraint account_trials_user_unica unique (user_id),
  constraint account_trials_fechas check (ends_at > started_at)
);

-- UNA prueba VIGENTE por RUT: índice único PARCIAL. Revocar la prueba de un
-- apropiador (revoked_at) libera el RUT para que el titular legítimo active
-- la suya. Un unique absoluto haría imposible ese procedimiento de reclamo.
create unique index if not exists account_trials_rut_activo_key
  on public.account_trials (rut_normalized)
  where revoked_at is null;

create or replace function public.touch_billing_identities()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists billing_identities_touch on public.billing_identities;
create trigger billing_identities_touch
  before update on public.billing_identities
  for each row execute function public.touch_billing_identities();

-- ── 3. RLS: el dueño LEE lo suyo; NADIE escribe directo ─────────────────────
-- Todas las escrituras pasan por la RPC (service_role). Los usuarios
-- autenticados no pueden insertar trials ni alterar started_at/ends_at/
-- revoked_at/rut: sin grants de escritura y sin políticas de escritura.

alter table public.billing_identities enable row level security;
alter table public.account_trials enable row level security;

drop policy if exists "billing_identities_select_own" on public.billing_identities;
create policy "billing_identities_select_own" on public.billing_identities
  for select to authenticated using (auth.uid() = user_id);

drop policy if exists "account_trials_select_own" on public.account_trials;
create policy "account_trials_select_own" on public.account_trials
  for select to authenticated using (auth.uid() = user_id);

revoke all on public.billing_identities from anon, authenticated;
revoke all on public.account_trials from anon, authenticated;
grant select on public.billing_identities to authenticated;
grant select on public.account_trials to authenticated;
grant all on public.billing_identities to service_role;
grant all on public.account_trials to service_role;

-- ── 4. RPC atómica de activación ─────────────────────────────────────────────
-- Errores tipados (la API los traduce): los del PROPIO solicitante son
-- específicos; los que involucran a terceros colapsan al genérico en la API
-- (no se revela qué cuenta usó un RUT — anti-enumeración de clientes).

create or replace function public.activate_account_trial(
  p_user_id uuid,
  p_rut_type text,
  p_rut text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_uid uuid;
  v_rut text;
  v_identity uuid;
  v_started timestamptz;
  v_ends timestamptz;
begin
  -- auth.uid() manda; p_user_id solo se honra en el camino service_role
  -- (la API ya validó el JWT). Un cliente jamás ejecuta esta función
  -- directamente: EXECUTE está revocado para anon/authenticated.
  v_uid := coalesce(auth.uid(), p_user_id);
  if v_uid is null then
    return jsonb_build_object('ok', false, 'error', 'TRIAL_NOT_ELIGIBLE');
  end if;
  if p_rut_type not in ('empresa', 'responsable') then
    return jsonb_build_object('ok', false, 'error', 'INVALID_RUT');
  end if;

  v_rut := public.normalize_rut(p_rut);
  if v_rut is null or not public.rut_dv_valido(v_rut) then
    return jsonb_build_object('ok', false, 'error', 'INVALID_RUT');
  end if;

  -- Una prueba por usuario, revocada o no (el constraint igual lo garantiza;
  -- este check da el código correcto sin depender del orden de inserción).
  if exists (select 1 from public.account_trials t where t.user_id = v_uid) then
    return jsonb_build_object('ok', false, 'error', 'USER_ALREADY_USED_TRIAL');
  end if;

  -- La unicidad por RUT es SOLO por número normalizado — jamás por
  -- (tipo, número): alternar "empresa"/"responsable" no duplica la prueba.
  insert into public.billing_identities (user_id, rut_type, rut_normalized, rut_masked)
  values (v_uid, p_rut_type, v_rut, public.mask_rut(v_rut))
  on conflict (user_id, rut_normalized)
  do update set rut_type = excluded.rut_type
  returning id into v_identity;

  v_started := now();
  v_ends := v_started + interval '15 days';

  begin
    insert into public.account_trials
      (user_id, billing_identity_id, rut_normalized, started_at, ends_at)
    values (v_uid, v_identity, v_rut, v_started, v_ends);
  exception
    when unique_violation then
      -- Carrera perdida: otro insert ganó entre el check y el nuestro.
      if exists (select 1 from public.account_trials t where t.user_id = v_uid) then
        return jsonb_build_object('ok', false, 'error', 'USER_ALREADY_USED_TRIAL');
      end if;
      return jsonb_build_object('ok', false, 'error', 'RUT_ALREADY_USED_TRIAL');
  end;

  return jsonb_build_object(
    'ok', true,
    'trial', jsonb_build_object(
      'started_at', v_started,
      'ends_at', v_ends,
      'revoked_at', null
    )
  );
end;
$$;

revoke all on function public.activate_account_trial(uuid, text, text) from public;
revoke all on function public.activate_account_trial(uuid, text, text) from anon;
revoke all on function public.activate_account_trial(uuid, text, text) from authenticated;
grant execute on function public.activate_account_trial(uuid, text, text) to service_role;

-- ── 5. can_process_data(): la puerta comercial de RLS ────────────────────────
-- Sin parámetros y con auth.uid() interno: exponerla parametrizada a
-- authenticated sería un oráculo para sondear el estado comercial de otros
-- usuarios. El backend NO la llama para sus decisiones (usa su AccessContext
-- con service_role); el test de contrato de la API mantiene ambas alineadas.

create or replace function public.can_process_data()
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select
    coalesce(
      (
        select p.is_admin
               or coalesce(nullif(lower(trim(p.plan)), ''), 'basico')
                  not in ('sin_plan', 'ninguno', 'none', 'free')
        from public.profiles p
        where p.id = auth.uid()
      ),
      -- Sin fila en profiles (cuentas antiguas): protegidas por diseño,
      -- misma regla que normalize_plan() en la API.
      true
    )
    or exists (
      select 1
      from public.account_trials t
      where t.user_id = auth.uid()
        and t.revoked_at is null
        and t.started_at <= now()
        and now() < t.ends_at
    );
$$;

revoke all on function public.can_process_data() from public;
grant execute on function public.can_process_data() to authenticated;

-- ── 6. Políticas RESTRICTIVAS (se AND-ean con las permisivas de propiedad) ──
-- Solo bloquean ESCRITURAS nuevas (procesar/subir datos). La lectura sigue
-- intacta: al expirar la prueba, el usuario conserva Historial, Configuración
-- y sus archivos según retención — solo no puede seguir procesando.

drop policy if exists "datasets_requiere_acceso_comercial" on public.datasets;
create policy "datasets_requiere_acceso_comercial" on public.datasets
  as restrictive for insert to authenticated
  with check (public.can_process_data());

drop policy if exists "datasets_update_requiere_acceso_comercial" on public.datasets;
create policy "datasets_update_requiere_acceso_comercial" on public.datasets
  as restrictive for update to authenticated
  using (public.can_process_data())
  with check (public.can_process_data());

-- Storage: restringe SOLO el bucket de datasets (las políticas restrictivas
-- se AND-ean: sin la condición del bucket, bloquearía cualquier otro bucket).
drop policy if exists "storage_requiere_acceso_comercial" on storage.objects;
create policy "storage_requiere_acceso_comercial" on storage.objects
  as restrictive for insert to authenticated
  with check (bucket_id <> 'datasets' or public.can_process_data());

-- ============================================================================
-- Verificación rápida (opcional):
--   select public.normalize_rut('12.345.678-k');        -- → 12345678-K
--   select public.rut_dv_valido('12345678-5');          -- → true/false
--   select public.can_process_data();                   -- como authenticated
-- Recordatorio: la política de contraseñas (mínimo 8, letras y números) se
-- configura en Supabase → Authentication → Providers → Email (no es SQL).
-- ============================================================================
