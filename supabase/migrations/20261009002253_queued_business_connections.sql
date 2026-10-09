-- Business discovery and manual validation reuse the owner-scoped durable queue.
set local lock_timeout = '5s';
alter table app_private.analysis_queue_jobs
  drop constraint analysis_queue_jobs_kind_check;
alter table app_private.analysis_queue_jobs
  add constraint analysis_queue_jobs_kind_check check
  (kind in ('metrics', 'standardize', 'standardize_batch', 'clean_batch', 'clean_export',
            'relationships', 'relationship_catalog', 'relationship_dashboard'));
