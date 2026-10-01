begin;

-- This minimal ledger must survive deletion and can be exported separately
-- from ordinary backups. It contains no UUID, email, filename or request text.
create table app_private.erasure_tombstones (
  subject_digest text primary key check (subject_digest ~ '^[0-9a-f]{64}$'),
  erased_at timestamptz not null,
  receipt_id uuid not null unique,
  created_at timestamptz not null default now()
);
alter table app_private.erasure_tombstones enable row level security;
revoke all on app_private.erasure_tombstones from public, anon, authenticated;
grant select, insert on app_private.erasure_tombstones to service_role;

create function app_private.capture_erasure_tombstone() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.status='completed' and old.status is distinct from 'completed' then
    insert into app_private.erasure_tombstones(subject_digest,erased_at,receipt_id)
      values(new.subject_digest,coalesce(new.completed_at,now()),new.id)
      on conflict (subject_digest) do update
        set erased_at=greatest(app_private.erasure_tombstones.erased_at,excluded.erased_at),
            receipt_id=excluded.receipt_id;
    -- Audit retains the action and receipt IDs, but no direct subject UUID.
    update public.admin_audit set target_user_id=null
      where target_user_id=old.target_user_id;
  end if;
  return new;
end;
$$;
revoke all on function app_private.capture_erasure_tombstone() from public,anon,authenticated;

create trigger capture_account_erasure_tombstone
after update of status on app_private.account_erasure_jobs
for each row execute function app_private.capture_erasure_tombstone();

insert into app_private.erasure_tombstones(subject_digest,erased_at,receipt_id)
select subject_digest,coalesce(completed_at,updated_at),id
from app_private.account_erasure_jobs where status='completed'
on conflict (subject_digest) do nothing;

commit;
