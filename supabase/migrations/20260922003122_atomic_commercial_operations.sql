begin;

alter table public.ai_usage
  add column reservation_id uuid unique,
  add column state text not null default 'used'
    check (state in ('reserved', 'used', 'released')),
  add column addon_debited boolean not null default false;

-- Old usage remains charged. Pending/uncertain provider calls hold their quota;
-- there is deliberately no TTL refund that could fund repeated timed-out calls.
create or replace function public.reserve_ai_quota(
  p_user_id uuid, p_reservation_id uuid, p_kind text, p_limits jsonb
) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare
  account public.profiles%rowtype;
  existing public.ai_usage%rowtype;
  used_count bigint;
  allowed integer;
  addons bigint := 0;
  debit boolean := false;
  month_start timestamptz := date_trunc('month', now() at time zone 'UTC') at time zone 'UTC';
begin
  if p_user_id is null or p_reservation_id is null
     or p_kind not in ('summary', 'chat', 'recommendation', 'cleaning') then
    raise exception using errcode = '22023', message = 'invalid_quota_request';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('quota:' || p_user_id::text, 0));
  select * into account from public.profiles where id = p_user_id for share;
  if not found then raise exception using errcode = 'P0002', message = 'account_not_found'; end if;
  select * into existing from public.ai_usage where reservation_id = p_reservation_id;
  if found then
    -- Never authorize another provider call for a replayed reservation.
    raise exception using errcode = '23505', message = 'reservation_already_exists';
  end if;
  allowed := coalesce((p_limits ->> account.plan)::integer, 0);
  if allowed < 0 or allowed > 10000 then
    raise exception using errcode = '22023', message = 'invalid_quota_limit';
  end if;
  if not account.is_admin and (allowed = 0 or
     (p_kind = 'cleaning' and account.plan not in ('analista', 'gold'))) then
    return jsonb_build_object('allowed', false, 'reason', 'plan');
  end if;
  -- Shared rolling burst limit across processes and replicas, including admins.
  if p_kind <> 'cleaning' and (select count(*) from public.ai_usage
      where user_id = p_user_id and kind <> 'cleaning'
        and created_at > now() - interval '60 seconds') >= 12 then
    return jsonb_build_object('allowed', false, 'reason', 'burst');
  end if;
  select count(*) into used_count from public.ai_usage
    where user_id = p_user_id and created_at >= month_start and state <> 'released'
      and ((p_kind = 'cleaning' and kind = 'cleaning') or
           (p_kind <> 'cleaning' and kind <> 'cleaning'));
  if p_kind = 'cleaning' then
    select coalesce(sum(credits), 0) into addons from public.plan_addons where user_id = p_user_id;
  end if;
  if not account.is_admin and used_count >= allowed then
    if p_kind <> 'cleaning' or addons <= 0 then
      return jsonb_build_object('allowed', false, 'reason', 'quota');
    end if;
    debit := true;
    insert into public.plan_addons (user_id, credits, granted_by, note)
      values (p_user_id, -1, 'sistema', 'Reserva limpieza: ' || p_reservation_id::text);
  end if;
  insert into public.ai_usage (user_id, kind, reservation_id, state, addon_debited)
    values (p_user_id, p_kind, p_reservation_id, 'reserved', debit);
  return jsonb_build_object('allowed', true, 'reservation_id', p_reservation_id,
    'plan', account.plan, 'usadas_mes', used_count, 'usadas', used_count,
    'base', allowed, 'limite', allowed, 'addons', addons, 'consume_addon', debit,
    'ilimitado', account.is_admin);
end;
$$;

create or replace function public.settle_ai_quota(
  p_user_id uuid, p_reservation_id uuid, p_success boolean
) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare entry public.ai_usage%rowtype;
begin
  if p_success is null then raise exception 'invalid_settlement'; end if;
  perform pg_advisory_xact_lock(hashtextextended('quota:' || p_user_id::text, 0));
  select * into entry from public.ai_usage
    where user_id = p_user_id and reservation_id = p_reservation_id for update;
  if not found then raise exception using errcode = 'P0002', message = 'reservation_not_found'; end if;
  if entry.state <> 'reserved' then
    return jsonb_build_object('state', entry.state, 'applied', false);
  end if;
  -- Only local deterministic cleaning can be refunded automatically. An AI
  -- timeout/cancellation is not proof that the upstream provider did no work.
  if not p_success and entry.kind <> 'cleaning' then
    raise exception using errcode = '22023', message = 'provider_reconciliation_required';
  end if;
  if not p_success and entry.addon_debited then
    insert into public.plan_addons (user_id, credits, granted_by, note)
      values (p_user_id, 1, 'sistema', 'Reintegro limpieza: ' || p_reservation_id::text);
  end if;
  update public.ai_usage set state = case when p_success then 'used' else 'released' end
    where id = entry.id;
  return jsonb_build_object('state', case when p_success then 'used' else 'released' end,
                           'applied', true);
end;
$$;

create or replace function public.cleaning_addons_balance(p_user_id uuid) returns bigint
language sql stable security invoker set search_path = '' as $$
  select coalesce(sum(credits), 0)::bigint from public.plan_addons where user_id = p_user_id;
$$;

revoke all on function public.reserve_ai_quota(uuid, uuid, text, jsonb) from public, anon, authenticated;
revoke all on function public.settle_ai_quota(uuid, uuid, boolean) from public, anon, authenticated;
revoke all on function public.cleaning_addons_balance(uuid) from public, anon, authenticated;
grant execute on function public.reserve_ai_quota(uuid, uuid, text, jsonb) to service_role;
grant execute on function public.settle_ai_quota(uuid, uuid, boolean) to service_role;
grant execute on function public.cleaning_addons_balance(uuid) to service_role;

-- Serialize before checking idempotency. Concurrent identical grants now
-- return the same result instead of failing on the ledger's unique key.
create or replace function public.adjust_ads_coins(
  p_user_id uuid, p_amount bigint, p_reason text, p_reference_key text,
  p_metadata jsonb default '{}'::jsonb
) returns table(balance bigint, applied boolean)
language plpgsql security invoker set search_path = '' as $$
declare current_balance bigint; previous public.ads_coin_transactions%rowtype;
begin
  if p_user_id is null or p_amount is null or p_amount = 0
     or coalesce(btrim(p_reason), '') = '' or coalesce(btrim(p_reference_key), '') = ''
     or length(p_reference_key) > 200 or length(p_reason) > 100
     or pg_column_size(p_metadata) > 8192 then
    raise exception using errcode = '22023', message = 'invalid_coin_adjustment';
  end if;
  insert into public.ads_coin_wallets (user_id) values (p_user_id)
    on conflict (user_id) do nothing;
  select w.balance into current_balance from public.ads_coin_wallets w
    where w.user_id = p_user_id for update;
  select * into previous from public.ads_coin_transactions
    where user_id = p_user_id and reference_key = p_reference_key;
  if found then
    if previous.amount <> p_amount or previous.reason <> p_reason
       or previous.metadata <> coalesce(p_metadata, '{}'::jsonb) then
      raise exception using errcode = '22023', message = 'coin_reference_conflict';
    end if;
    return query select previous.balance_after, false;
    return;
  end if;
  if current_balance + p_amount < 0 then raise exception 'insufficient_ads_coins'; end if;
  current_balance := current_balance + p_amount;
  update public.ads_coin_wallets set balance = current_balance,
    lifetime_earned = lifetime_earned + greatest(p_amount, 0),
    lifetime_spent = lifetime_spent + greatest(-p_amount, 0), updated_at = now()
    where user_id = p_user_id;
  insert into public.ads_coin_transactions
    (user_id, amount, reason, reference_key, balance_after, metadata)
    values (p_user_id, p_amount, p_reason, p_reference_key, current_balance, coalesce(p_metadata, '{}'::jsonb));
  return query select current_balance, true;
end;
$$;

create or replace function public.ensure_monthly_ads_allowance(p_user_id uuid) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare
  account public.profiles%rowtype;
  allowance integer;
  credited bigint;
  period text := to_char(now() at time zone 'UTC', 'YYYY-MM');
begin
  select * into account from public.profiles where id = p_user_id for share;
  if not found then raise exception using errcode = 'P0002', message = 'account_not_found'; end if;
  allowance := case when account.is_admin then 2500 else
    case account.plan when 'basico' then 100 when 'analista' then 500 when 'gold' then 1200 else 0 end end;
  insert into public.ads_coin_wallets (user_id) values (p_user_id) on conflict (user_id) do nothing;
  perform 1 from public.ads_coin_wallets where user_id = p_user_id for update;
  select coalesce(sum(amount), 0) into credited from public.ads_coin_transactions
    where user_id = p_user_id and reason = 'plan_monthly_allowance' and metadata ->> 'month' = period;
  if credited < allowance then
    perform public.adjust_ads_coins(p_user_id, allowance - credited, 'plan_monthly_allowance',
      'allowance:' || period || ':' || allowance::text,
      jsonb_build_object('plan', account.plan, 'month', period));
  end if;
  return jsonb_build_object('plan', account.plan, 'monthly_allowance', allowance);
end;
$$;
revoke all on function public.adjust_ads_coins(uuid, bigint, text, text, jsonb) from public, anon, authenticated;
grant execute on function public.adjust_ads_coins(uuid, bigint, text, text, jsonb) to service_role;
revoke all on function public.ensure_monthly_ads_allowance(uuid) from public, anon, authenticated;
grant execute on function public.ensure_monthly_ads_allowance(uuid) to service_role;

alter table public.admin_audit add column operation_id uuid;
create unique index admin_audit_operation_unique on public.admin_audit(admin_id, operation_id);

create or replace function public.admin_commercial_operation(
  p_admin_id uuid, p_operation_id uuid, p_target_user_id uuid, p_action text, p_payload jsonb
) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare
  admin_ok boolean;
  previous public.admin_audit%rowtype;
  normalized_plan text;
  amount integer;
  coin_balance bigint;
  result jsonb;
begin
  if p_operation_id is null or p_target_user_id is null or p_payload is null
     or jsonb_typeof(p_payload) <> 'object' or pg_column_size(p_payload) > 8192 then
    raise exception using errcode = '22023', message = 'invalid_admin_operation';
  end if;
  -- Lock only the actor while authorizing; no email or JWT metadata bypass.
  select is_admin into admin_ok from public.profiles where id = p_admin_id for share;
  if admin_ok is distinct from true then
    raise exception using errcode = '42501', message = 'admin_required';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('admin:' || p_admin_id::text || ':' || p_operation_id::text, 0));
  select * into previous from public.admin_audit where admin_id = p_admin_id and operation_id = p_operation_id;
  if found then
    if previous.action <> p_action or previous.target_user_id <> p_target_user_id
       or previous.detail -> 'payload' <> p_payload then
      raise exception using errcode = '22023', message = 'admin_operation_conflict';
    end if;
    return previous.detail -> 'result';
  end if;
  perform 1 from public.profiles where id = p_target_user_id;
  if not found then raise exception using errcode = 'P0002', message = 'account_not_found'; end if;
  if p_action = 'set_plan' then
    normalized_plan := p_payload ->> 'plan';
    if normalized_plan is null or normalized_plan not in ('basico', 'analista', 'gold') then
      raise exception using errcode = '22023', message = 'invalid_plan';
    end if;
    update public.profiles set plan = normalized_plan where id = p_target_user_id;
    result := jsonb_build_object('ok', true, 'user_id', p_target_user_id, 'plan', normalized_plan);
  elsif p_action = 'grant_credits' then
    amount := (p_payload ->> 'credits')::integer;
    if amount is null or amount not between 1 and 1000 or length(p_payload ->> 'note') > 300 then
      raise exception using errcode = '22023', message = 'invalid_credits';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('quota:' || p_target_user_id::text, 0));
    insert into public.plan_addons (user_id, credits, granted_by, note)
      values (p_target_user_id, amount, p_admin_id::text, p_payload ->> 'note');
    result := jsonb_build_object('otorgado', true, 'user_id', p_target_user_id, 'credits', amount,
      'saldo', public.cleaning_addons_balance(p_target_user_id));
  elsif p_action = 'grant_ads_coins' then
    amount := (p_payload ->> 'amount')::integer;
    if amount is null or amount not between 1 and 1000000 or length(p_payload ->> 'note') > 300 then
      raise exception using errcode = '22023', message = 'invalid_coins';
    end if;
    select c.balance into coin_balance from public.adjust_ads_coins(p_target_user_id, amount,
      'admin_grant', 'admin:' || p_admin_id::text || ':' || p_operation_id::text,
      jsonb_build_object('note', p_payload ->> 'note')) c;
    result := jsonb_build_object('ok', true, 'balance', coin_balance, 'amount', amount);
  else
    raise exception using errcode = '22023', message = 'invalid_admin_action';
  end if;
  -- Any audit failure rolls back the entitlement/ledger mutation above.
  insert into public.admin_audit(admin_id, target_user_id, action, operation_id, detail)
    values(p_admin_id, p_target_user_id, p_action, p_operation_id,
      jsonb_build_object('payload', p_payload, 'result', result));
  return result;
end;
$$;
revoke all on function public.admin_commercial_operation(uuid, uuid, uuid, text, jsonb)
  from public, anon, authenticated;
grant execute on function public.admin_commercial_operation(uuid, uuid, uuid, text, jsonb) to service_role;

commit;
