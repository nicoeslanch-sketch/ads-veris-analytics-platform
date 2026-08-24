-- Soporte conversacional, ADS Coins y fuentes Google Sheets persistentes.
-- Migracion aditiva: no modifica ni elimina solicitudes, datasets o creditos existentes.

create table public.support_conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  status text not null default 'open'
    constraint support_conversations_status_check check (status in ('open', 'closed')),
  source_page text,
  created_at timestamptz not null default now(),
  last_message_at timestamptz not null default now(),
  closed_at timestamptz,
  closed_by uuid references auth.users (id) on delete set null
);

create index support_conversations_user_idx
  on public.support_conversations (user_id, last_message_at desc);
create index support_conversations_expiry_idx
  on public.support_conversations (last_message_at);
create unique index support_conversations_one_open_per_user_idx
  on public.support_conversations (user_id) where status = 'open';

create table public.support_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.support_conversations (id) on delete cascade,
  sender_id uuid references auth.users (id) on delete set null,
  sender_role text not null
    constraint support_messages_sender_role_check check (sender_role in ('customer', 'admin', 'system')),
  body text not null
    constraint support_messages_body_check check (char_length(btrim(body)) between 1 and 4000),
  created_at timestamptz not null default now()
);

create index support_messages_conversation_idx
  on public.support_messages (conversation_id, created_at);

create or replace function public.touch_support_conversation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  update public.support_conversations
  set last_message_at = new.created_at
  where id = new.conversation_id;
  return new;
end;
$$;

create trigger support_messages_touch_conversation
  after insert on public.support_messages
  for each row execute function public.touch_support_conversation();

alter table public.support_conversations enable row level security;
alter table public.support_messages enable row level security;
revoke all on table public.support_conversations from anon, authenticated;
revoke all on table public.support_messages from anon, authenticated;
grant select on table public.support_conversations to authenticated;
grant select on table public.support_messages to authenticated;
grant all privileges on table public.support_conversations to service_role;
grant all privileges on table public.support_messages to service_role;

create policy "support_conversations_select_own"
  on public.support_conversations for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "support_messages_select_own"
  on public.support_messages for select to authenticated
  using (exists (
    select 1 from public.support_conversations conversation
    where conversation.id = conversation_id
      and conversation.user_id = (select auth.uid())
  ));

-- La eliminacion es real, como pide el producto: mensajes y conversacion se
-- borran al cumplir 24 horas sin actividad. El backend ejecuta la misma poda
-- al recibir trafico y pg_cron la garantiza aun cuando nadie abre la app.
create or replace function public.purge_stale_support_conversations()
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  deleted_count bigint;
begin
  delete from public.support_conversations
  where last_message_at < now() - interval '24 hours';
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

revoke all on function public.purge_stale_support_conversations() from public, anon, authenticated;
grant execute on function public.purge_stale_support_conversations() to service_role;

do $$
begin
  create extension if not exists pg_cron with schema pg_catalog;
exception when insufficient_privilege then
  raise notice 'pg_cron no disponible; la poda oportunista del backend sigue activa';
end $$;

do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron')
     and not exists (select 1 from cron.job where jobname = 'ads-veris-support-expiry') then
    perform cron.schedule(
      'ads-veris-support-expiry',
      '17 * * * *',
      'select public.purge_stale_support_conversations();'
    );
  end if;
end $$;

-- Base editable del bot determinista. El backend incluye un catalogo de
-- respaldo versionado para que Ayuda rapida funcione incluso durante una
-- recuperacion de base de datos.
create table public.support_bot_articles (
  id uuid primary key default gen_random_uuid(),
  key text not null unique,
  category text not null,
  title text not null,
  triggers text[] not null default '{}',
  response text not null,
  follow_up text,
  priority integer not null default 50,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index support_bot_articles_active_idx
  on public.support_bot_articles (active, priority desc);
alter table public.support_bot_articles enable row level security;
revoke all on table public.support_bot_articles from anon, authenticated;
grant all privileges on table public.support_bot_articles to service_role;

-- Billetera unificada. No se habilitan compras ni IA por esta migracion; solo
-- queda listo el ledger auditable y atomico para activarlos por feature flag.
create table public.ads_coin_wallets (
  user_id uuid primary key references auth.users (id) on delete cascade,
  balance bigint not null default 0 constraint ads_coin_balance_check check (balance >= 0),
  lifetime_earned bigint not null default 0 constraint ads_coin_earned_check check (lifetime_earned >= 0),
  lifetime_spent bigint not null default 0 constraint ads_coin_spent_check check (lifetime_spent >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.ads_coin_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  amount bigint not null constraint ads_coin_amount_check check (amount <> 0),
  reason text not null,
  reference_key text not null,
  balance_after bigint not null constraint ads_coin_after_check check (balance_after >= 0),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (user_id, reference_key)
);

create index ads_coin_transactions_user_idx
  on public.ads_coin_transactions (user_id, created_at desc);
alter table public.ads_coin_wallets enable row level security;
alter table public.ads_coin_transactions enable row level security;
revoke all on table public.ads_coin_wallets from anon, authenticated;
revoke all on table public.ads_coin_transactions from anon, authenticated;
grant select on table public.ads_coin_wallets to authenticated;
grant select on table public.ads_coin_transactions to authenticated;
grant all privileges on table public.ads_coin_wallets to service_role;
grant all privileges on table public.ads_coin_transactions to service_role;

create policy "ads_coin_wallets_select_own"
  on public.ads_coin_wallets for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "ads_coin_transactions_select_own"
  on public.ads_coin_transactions for select to authenticated
  using ((select auth.uid()) = user_id);

create or replace function public.adjust_ads_coins(
  p_user_id uuid,
  p_amount bigint,
  p_reason text,
  p_reference_key text,
  p_metadata jsonb default '{}'::jsonb
)
returns table(balance bigint, applied boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
  current_balance bigint;
  existing_balance bigint;
begin
  if p_amount = 0 or btrim(p_reason) = '' or btrim(p_reference_key) = '' then
    raise exception 'invalid_coin_adjustment';
  end if;

  select tx.balance_after into existing_balance
  from public.ads_coin_transactions tx
  where tx.user_id = p_user_id
    and tx.reference_key = p_reference_key;
  if found then
    return query select existing_balance, false;
    return;
  end if;

  insert into public.ads_coin_wallets (user_id)
  values (p_user_id)
  on conflict (user_id) do nothing;

  select wallet.balance into current_balance
  from public.ads_coin_wallets wallet
  where wallet.user_id = p_user_id
  for update;

  if current_balance + p_amount < 0 then
    raise exception 'insufficient_ads_coins';
  end if;

  current_balance := current_balance + p_amount;
  update public.ads_coin_wallets
  set balance = current_balance,
      lifetime_earned = lifetime_earned + greatest(p_amount, 0),
      lifetime_spent = lifetime_spent + greatest(-p_amount, 0),
      updated_at = now()
  where user_id = p_user_id;

  insert into public.ads_coin_transactions
    (user_id, amount, reason, reference_key, balance_after, metadata)
  values
    (p_user_id, p_amount, p_reason, p_reference_key, current_balance, coalesce(p_metadata, '{}'::jsonb));

  return query select current_balance, true;
end;
$$;

revoke all on function public.adjust_ads_coins(uuid, bigint, text, text, jsonb)
  from public, anon, authenticated;
grant execute on function public.adjust_ads_coins(uuid, bigint, text, text, jsonb)
  to service_role;

-- Una fuente representa una pestana concreta (gid) de un documento publico.
-- Varios enlaces o varias pestanas se guardan como fuentes independientes.
create table public.google_sheet_sources (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  dataset_id uuid references public.datasets (id) on delete set null,
  source_url text not null,
  sheet_id text not null,
  gid text not null default '0',
  display_name text not null,
  sync_mode text not null default 'manual'
    constraint google_sheet_sync_mode_check check (sync_mode in ('manual', 'automatic')),
  content_hash text,
  remote_hash text,
  update_available boolean not null default false,
  last_status text not null default 'connected'
    constraint google_sheet_status_check check (last_status in ('connected', 'changed', 'error')),
  last_error text,
  last_checked_at timestamptz,
  last_synced_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, sheet_id, gid)
);

create index google_sheet_sources_user_idx
  on public.google_sheet_sources (user_id, updated_at desc);
alter table public.google_sheet_sources enable row level security;
revoke all on table public.google_sheet_sources from anon, authenticated;
grant select on table public.google_sheet_sources to authenticated;
grant all privileges on table public.google_sheet_sources to service_role;
create policy "google_sheet_sources_select_own"
  on public.google_sheet_sources for select to authenticated
  using ((select auth.uid()) = user_id);

create trigger support_bot_articles_set_updated_at
  before update on public.support_bot_articles
  for each row execute procedure public.set_updated_at();
create trigger ads_coin_wallets_set_updated_at
  before update on public.ads_coin_wallets
  for each row execute procedure public.set_updated_at();
create trigger google_sheet_sources_set_updated_at
  before update on public.google_sheet_sources
  for each row execute procedure public.set_updated_at();

comment on table public.support_conversations is
  'Conversaciones humanas usuario-administrador; caducan tras 24 horas de inactividad.';
comment on table public.support_bot_articles is
  'Conocimiento editable del bot determinista, sin llamadas a modelos de IA.';
comment on table public.ads_coin_transactions is
  'Ledger inmutable e idempotente de ADS Coins.';
comment on table public.google_sheet_sources is
  'Conexiones persistentes a pestanas publicas de Google Sheets.';
