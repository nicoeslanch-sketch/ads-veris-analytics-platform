begin;

-- Revoked JWTs can still have a valid signature. Check the authoritative session.
create function app_private.account_session_active(p_user_id uuid, p_session_id uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from auth.sessions s join auth.users u on u.id = s.user_id
    where s.id = p_session_id and s.user_id = p_user_id
      and (s.not_after is null or s.not_after > now())
      and u.deleted_at is null and (u.banned_until is null or u.banned_until <= now())
  );
$$;
revoke all on function app_private.account_session_active(uuid,uuid) from public,anon,authenticated;
grant execute on function app_private.account_session_active(uuid,uuid) to service_role;

create function public.verified_session_context(p_user_id uuid, p_session_id uuid)
returns jsonb language sql stable security definer set search_path = '' as $$
  select app_private.account_security_context(p_user_id) || jsonb_build_object(
    'session_active', app_private.account_session_active(p_user_id, p_session_id));
$$;
revoke all on function public.verified_session_context(uuid,uuid) from public,anon,authenticated;
grant execute on function public.verified_session_context(uuid,uuid) to service_role;

-- Existing restrictive policies cover every public RLS table and Storage.
create or replace function app_private.session_mfa_satisfied() returns boolean
language sql stable security definer set search_path = '' as $$
  select app_private.account_session_active(auth.uid(), case
    when auth.jwt()->>'session_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
      then (auth.jwt()->>'session_id')::uuid else null end)
    and (
      coalesce(auth.jwt()->>'aal','aal1')='aal2'
      or (not exists(select 1 from public.profiles where id=auth.uid() and is_admin)
          and not exists(select 1 from auth.mfa_factors where user_id=auth.uid() and status='verified'))
    );
$$;
revoke all on function app_private.session_mfa_satisfied() from public,anon;
grant execute on function app_private.session_mfa_satisfied() to authenticated;
commit;
