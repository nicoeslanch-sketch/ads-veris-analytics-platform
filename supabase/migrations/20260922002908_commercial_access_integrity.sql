begin;

-- Preserve the source but detach any historical cross-owner reference.
update public.google_sheet_sources s
set dataset_id = null, last_status = 'error',
    last_error = 'Vuelve a vincular un archivo de tu cuenta.'
from public.datasets d
where s.dataset_id = d.id and s.user_id <> d.user_id;

create unique index datasets_id_owner_unique on public.datasets (id, user_id);
create index google_sheet_sources_dataset_owner_idx
  on public.google_sheet_sources (dataset_id, user_id);
alter table public.google_sheet_sources
  drop constraint google_sheet_sources_dataset_id_fkey,
  add constraint google_sheet_sources_dataset_owner_fkey
    foreign key (dataset_id, user_id) references public.datasets (id, user_id)
    on delete set null (dataset_id);

commit;
