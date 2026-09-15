-- Activate only after /storage/upload and its frontend client are deployed.
-- Server writers reserve durable capacity. Reads and existing objects are unchanged.
-- Existing read and deletion policies are not changed by this migration.
create policy datasets_require_managed_insert on storage.objects
  as restrictive for insert to authenticated
  with check (bucket_id <> 'datasets');
create policy datasets_require_managed_update on storage.objects
  as restrictive for update to authenticated
  using (bucket_id <> 'datasets') with check (bucket_id <> 'datasets');
