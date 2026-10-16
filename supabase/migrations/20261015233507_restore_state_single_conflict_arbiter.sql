-- The dataset primary key already implies uniqueness of (dataset_id, user_id).
-- The redundant unique index is not an ON CONFLICT (dataset_id) arbiter and
-- can reject concurrent first-sheet upserts with 23505. Keep the primary key,
-- ownership checks, RLS, foreign keys and revision guards unchanged.
begin;
set local lock_timeout = '5s';
alter table public.dataset_restore_states
  drop constraint if exists dataset_restore_states_dataset_id_user_id_key;
commit;
