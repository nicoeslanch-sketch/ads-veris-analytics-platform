begin;

-- Only booleans leave auth; factor secrets never become accessible to the API.
create function app_private.account_security_context(p_user_id uuid) returns jsonb
language sql stable security definer set search_path = '' as $$
  select jsonb_build_object(
    'is_admin', coalesce((select is_admin from public.profiles where id=p_user_id), false),
    'has_mfa', exists(select 1 from auth.mfa_factors where user_id=p_user_id and status='verified')
  );
$$;
revoke all on function app_private.account_security_context(uuid) from public,anon,authenticated;
grant execute on function app_private.account_security_context(uuid) to service_role;

create function public.session_security_context(p_user_id uuid) returns jsonb
language sql stable security invoker set search_path = '' as $$
  select app_private.account_security_context(p_user_id);
$$;
revoke all on function public.session_security_context(uuid) from public,anon,authenticated;
grant execute on function public.session_security_context(uuid) to service_role;

-- No user argument: authenticated clients can inspect only their own gate.
create function app_private.session_mfa_satisfied() returns boolean
language sql stable security definer set search_path = '' as $$
  select auth.uid() is not null and (
    coalesce(auth.jwt()->>'aal','aal1')='aal2'
    or (not exists(select 1 from public.profiles where id=auth.uid() and is_admin)
        and not exists(select 1 from auth.mfa_factors where user_id=auth.uid() and status='verified'))
  );
$$;
revoke all on function app_private.session_mfa_satisfied() from public,anon;
grant usage on schema app_private to authenticated;
grant execute on function app_private.session_mfa_satisfied() to authenticated;

commit;
