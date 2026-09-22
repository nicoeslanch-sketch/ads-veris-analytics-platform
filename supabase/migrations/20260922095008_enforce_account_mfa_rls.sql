begin;
-- Deploy the enrollment UI/API before applying this enforcement step in production.
-- Restrictive policies intersect existing ownership policies; they never grant access.
do $$ declare relation record; begin
  for relation in select tablename from pg_tables where schemaname='public' and rowsecurity loop
    execute format('create policy account_mfa_guard on public.%I as restrictive for all to authenticated '
      'using ((select app_private.session_mfa_satisfied())) '
      'with check ((select app_private.session_mfa_satisfied()))', relation.tablename);
  end loop;
end $$;
create policy account_mfa_guard on storage.objects as restrictive for all to authenticated
  using ((select app_private.session_mfa_satisfied()))
  with check ((select app_private.session_mfa_satisfied()));
commit;
