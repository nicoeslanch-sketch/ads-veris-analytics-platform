-- Reuse the bounded queue, ownership checks and leases for interactive relations.
alter table app_private.analysis_queue_jobs
  drop constraint analysis_queue_jobs_kind_check;
alter table app_private.analysis_queue_jobs
  add constraint analysis_queue_jobs_kind_check check
  (kind in ('metrics', 'standardize_batch', 'clean_batch', 'clean_export',
            'relationship_catalog', 'relationship_dashboard'));
