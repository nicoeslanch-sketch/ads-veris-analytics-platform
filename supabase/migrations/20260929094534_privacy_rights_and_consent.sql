begin;

-- Versioned, server-timestamped evidence. Editable Auth metadata is not evidence.
create table public.legal_acceptances (
  user_id uuid not null references auth.users(id) on delete cascade,
  version text not null check (length(version) between 1 and 40),
  source text not null check (source in ('signup', 'account')),
  accepted_at timestamptz not null default now(),
  primary key (user_id, version)
);
create table public.privacy_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (kind in ('access', 'correction', 'erasure', 'objection')),
  status text not null default 'pending' check (status in ('pending', 'reviewing', 'resolved', 'rejected')),
  message text not null default '' check (length(message) <= 2000),
  response text not null default '' check (length(response) <= 2000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index privacy_requests_owner_created on public.privacy_requests(user_id, created_at desc);
create index privacy_requests_pending on public.privacy_requests(created_at)
  where status in ('pending', 'reviewing');
create unique index privacy_requests_one_open_kind on public.privacy_requests(user_id, kind)
  where status in ('pending', 'reviewing');

alter table public.legal_acceptances enable row level security;
alter table public.privacy_requests enable row level security;
revoke all on public.legal_acceptances, public.privacy_requests from public, anon, authenticated;
grant select on public.legal_acceptances, public.privacy_requests to authenticated;
grant all on public.legal_acceptances, public.privacy_requests to service_role;
create policy legal_acceptances_owner on public.legal_acceptances for select to authenticated
  using ((select auth.uid()) = user_id);
create policy privacy_requests_owner on public.privacy_requests for select to authenticated
  using ((select auth.uid()) = user_id);
create policy account_mfa_guard on public.legal_acceptances as restrictive for all to authenticated
  using ((select app_private.session_mfa_satisfied())) with check ((select app_private.session_mfa_satisfied()));
create policy account_mfa_guard on public.privacy_requests as restrictive for all to authenticated
  using ((select app_private.session_mfa_satisfied())) with check ((select app_private.session_mfa_satisfied()));

create function app_private.capture_signup_acceptance() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  -- Capture only the explicit current declaration at creation, never on metadata edits.
  -- Legacy accounts are not backfilled or presumed to have consented.
  if new.raw_user_meta_data->>'legal_version' = '2026-09-28'
     and new.raw_user_meta_data->'service_data_consent' = 'true'::jsonb then
    insert into public.legal_acceptances(user_id, version, source)
      values (new.id, '2026-09-28', 'signup');
  end if;
  return new;
end;
$$;
revoke all on function app_private.capture_signup_acceptance() from public, anon, authenticated;
create trigger capture_signup_acceptance after insert on auth.users
  for each row execute function app_private.capture_signup_acceptance();

create function public.account_privacy_state(p_user_id uuid) returns jsonb
language sql security definer set search_path = '' as $$
  select jsonb_build_object('accepted', exists(
    select 1 from public.legal_acceptances where user_id=p_user_id and version='2026-09-28'),
    'version', '2026-09-28', 'requests', coalesce((select jsonb_agg(to_jsonb(r)) from (
      select id, kind, status, message, response, created_at, updated_at from public.privacy_requests
      where user_id=p_user_id order by created_at desc limit 50
    ) r), '[]'::jsonb));
$$;
create function public.accept_account_legal(p_user_id uuid, p_version text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  if p_version is distinct from '2026-09-28' then
    raise exception 'Unsupported legal version' using errcode='22023';
  end if;
  insert into public.legal_acceptances(user_id, version, source) values(p_user_id, p_version, 'account')
    on conflict (user_id, version) do nothing;
  return public.account_privacy_state(p_user_id);
end;
$$;
create function public.create_privacy_request(p_user_id uuid, p_kind text, p_message text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare result public.privacy_requests%rowtype;
begin
  if p_kind is null or p_kind not in ('access','correction','erasure','objection')
     or p_message is null or length(p_message)>2000 then
    raise exception 'Invalid privacy request' using errcode='22023';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('privacy:' || p_user_id::text, 0));
  select * into result from public.privacy_requests
    where user_id=p_user_id and kind=p_kind and status in ('pending','reviewing');
  if not found then
    if (select count(*) from public.privacy_requests where user_id=p_user_id
        and created_at > now()-interval '1 day') >= 12 then
      raise exception 'Privacy request limit' using errcode='22023';
    end if;
    insert into public.privacy_requests(user_id,kind,message) values(p_user_id,p_kind,p_message)
      returning * into result;
  end if;
  return to_jsonb(result) - 'user_id';
end;
$$;
create function public.admin_privacy_requests(p_admin_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  if not exists(select 1 from public.profiles where id=p_admin_id and is_admin) then
    raise exception 'Admin required' using errcode='42501';
  end if;
  return coalesce((select jsonb_agg(to_jsonb(r)) from (
    select r.*, u.email from public.privacy_requests r join auth.users u on u.id=r.user_id
    order by (r.status in ('pending','reviewing')) desc, r.created_at asc limit 100
  ) r), '[]'::jsonb);
end;
$$;
create function public.resolve_privacy_request(p_admin_id uuid, p_request_id uuid, p_status text, p_response text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare target public.privacy_requests%rowtype;
begin
  if not exists(select 1 from public.profiles where id=p_admin_id and is_admin) then
    raise exception 'Admin required' using errcode='42501';
  end if;
  if p_status is null or p_status not in ('reviewing','resolved','rejected') or p_response is null
     or length(trim(p_response))<10 or length(p_response)>2000 then
    raise exception 'A documented response is required' using errcode='22023';
  end if;
  select * into target from public.privacy_requests where id=p_request_id for update;
  if not found then raise exception 'Request not found' using errcode='P0002'; end if;
  if target.status=p_status and target.response=p_response then return to_jsonb(target); end if;
  if target.status in ('resolved','rejected') then
    raise exception 'Request is already closed' using errcode='22023';
  end if;
  update public.privacy_requests set status=p_status,response=p_response,updated_at=now()
    where id=p_request_id returning * into target;
  insert into public.admin_audit(admin_id,target_user_id,action,detail)
    values(p_admin_id,target.user_id,'privacy_request_updated',
      jsonb_build_object('request_id',p_request_id,'status',p_status));
  return to_jsonb(target);
end;
$$;
revoke all on function public.account_privacy_state(uuid), public.accept_account_legal(uuid,text),
  public.create_privacy_request(uuid,text,text), public.admin_privacy_requests(uuid),
  public.resolve_privacy_request(uuid,uuid,text,text) from public, anon, authenticated;
grant execute on function public.account_privacy_state(uuid), public.accept_account_legal(uuid,text),
  public.create_privacy_request(uuid,text,text), public.admin_privacy_requests(uuid),
  public.resolve_privacy_request(uuid,uuid,text,text) to service_role;
commit;
