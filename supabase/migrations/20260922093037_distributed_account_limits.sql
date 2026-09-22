begin;

create table app_private.request_budgets (
  bucket_hash text primary key check (bucket_hash ~ '^[a-f0-9]{64}$'),
  attempts timestamptz[] not null default '{}',
  expires_at timestamptz not null
);
alter table app_private.request_budgets enable row level security;
revoke all on app_private.request_budgets from public,anon,authenticated;
grant all on app_private.request_budgets to service_role;
create index request_budgets_expiry_idx on app_private.request_budgets(expires_at);

create function public.consume_request_budget(p_bucket_hash text,p_limit integer,p_window_seconds integer)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare stamp timestamptz; recent timestamptz[]; retry integer;
begin
  if p_bucket_hash is null or p_bucket_hash !~ '^[a-f0-9]{64}$'
     or p_limit is null or p_limit not between 1 and 100
     or p_window_seconds is null or p_window_seconds not between 1 and 3600 then
    raise exception 'Invalid request budget' using errcode='22023';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('request-budget:'||p_bucket_hash,0));
  stamp := clock_timestamp();
  select coalesce(array_agg(a order by a),'{}'::timestamptz[]) into recent
    from app_private.request_budgets b cross join lateral unnest(b.attempts) a
    where b.bucket_hash=p_bucket_hash and a > stamp-make_interval(secs=>p_window_seconds);
  if cardinality(recent)>=p_limit then
    retry := greatest(1,ceil(extract(epoch from recent[1]+make_interval(secs=>p_window_seconds)-stamp))::integer);
    return jsonb_build_object('allowed',false,'retry_after',retry);
  end if;
  insert into app_private.request_budgets(bucket_hash,attempts,expires_at)
    values(p_bucket_hash,array_append(recent,stamp),stamp+make_interval(secs=>p_window_seconds))
    on conflict(bucket_hash) do update set attempts=excluded.attempts,expires_at=excluded.expires_at;
  -- Bounded opportunistic retention, with no locks on unrelated active budgets.
  delete from app_private.request_budgets where bucket_hash in (
    select bucket_hash from app_private.request_budgets where expires_at<stamp
    order by expires_at limit 100 for update skip locked);
  return jsonb_build_object('allowed',true,'retry_after',0);
end $$;
revoke all on function public.consume_request_budget(text,integer,integer) from public,anon,authenticated;
grant execute on function public.consume_request_budget(text,integer,integer) to service_role;

create function public.create_support_request_guarded(p_user_id uuid,p_message text,p_page text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare message text := btrim(p_message); created uuid;
begin
  if p_user_id is null or message is null or char_length(message) not between 1 and 2000
     or char_length(coalesce(p_page,''))>120 then
    raise exception 'Invalid support request' using errcode='22023';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('support-request:'||p_user_id::text,0));
  if exists(select 1 from public.support_requests where user_id=p_user_id and status='pendiente' and mensaje=message) then
    return jsonb_build_object('created',false,'reason','duplicate');
  end if;
  if (select count(*) from public.support_requests where user_id=p_user_id and status='pendiente')>=3 then
    return jsonb_build_object('created',false,'reason','pending_limit');
  end if;
  insert into public.support_requests(user_id,mensaje,pagina) values(p_user_id,message,nullif(btrim(p_page),''))
    returning id into created;
  return jsonb_build_object('created',true,'id',created);
end $$;
revoke all on function public.create_support_request_guarded(uuid,text,text) from public,anon,authenticated;
grant execute on function public.create_support_request_guarded(uuid,text,text) to service_role;

commit;
