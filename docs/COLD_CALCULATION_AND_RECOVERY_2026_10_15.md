# First-calculation optimization and recovery verification

## Relationship catalog

The catalog already classified each prepared sheet, but several pair-level
helpers repeated the same classification, including numerical evidence checks.
The optimization reuses classifications only within that call. Concatenated
sales create a different frame and are classified separately. No global cache,
ownership change, sampling, removed safety check or financial rule is introduced.

Local comparison against commit `82a6da5`, using the same prepared reference
workbook (22 selected sheets, 16,546 rows), with networking prohibited:

| Catalog calculation | Before | After |
| --- | ---: | ---: |
| Median of three runs | 7.162 s | 2.451 s |
| Sheet classifications per call | 472 | 21 |
| Safe relationships returned | 8 | 8 |

The complete serialized catalog was identical in all six runs. Measurements
alternated old/new order, used no catalog-result cache and excluded XLSX loading,
cleaning, HTTP, Storage and other dashboards. The 65.8% reduction applies only to
this local catalog calculation, not the whole upload or a Render response-time
guarantee. One header is absorbed by the existing document-line preparation,
explaining the 21 classifications for 22 selected sheets.

Regression tests assert a linear number of classifications, a separate combined
frame for multiple periods, and no reuse across requests. Replacing a dimension
with duplicate keys still removes the unsafe relationship.

After the change, the reference ledger, eight relationship dashboards and catalog
matched their previous complete JSON output. All 259 independent oracle checks
(global, monthly, annual and branch figures) passed again.

## Capacity workload

Automatic business discovery also reuses the full unfiltered analysis it has
already computed when constructing the response metrics. The reuse is local to
the current request, includes an unsupported (`None`) result and is explicitly
disabled when a date boundary or business filter is supplied. Tests cover these
guards and assert one business calculation in the automatic discovery path.

An alternating three-run local comparison of that discovery stage measured a
median of 9.325 s before and 6.365 s after (31.7% lower), with identical complete
responses. These timings exclude parsing/cleaning and cannot be added to the
catalog percentage or interpreted as production response-time guarantees.

The manual capacity workflow now offers `analysis=business` for its four-sheet
XLSX fixture. It consolidates three periods, joins product costs and verifies
both revenue and known cost against independent daily sums for every completed
job. `analysis=append` retains the older workload for comparison; business mode
rejects CSV rather than silently measuring a different path. Preparation,
persistence fault injection, worker-crash recovery, account isolation and the
global one-heavy-job limit remain enabled.

The first business-capacity run (`38823404964`) stopped before sustained load:
standardization succeeded, but one concurrent snapshot write returned PostgreSQL
23505. The schema had both a primary key on `dataset_id` and a redundant unique
constraint on `(dataset_id, user_id)`. Only the first is an arbiter for the RPC's
`ON CONFLICT (dataset_id)`. Migration `20261015233507` removes the redundant
constraint, not the primary key or any ownership/revision check. No foreign key
references that redundant constraint in the repository or the inspected live
schema. A database regression exercises 128 simultaneous first-sheet writes across
fresh datasets and both RPC versions, plus stale-revision and wrong-owner denials.
The failed run is not capacity evidence. The successful repeat is described below.

### Verified isolated run

[Run 38824606157](https://github.com/nicoeslanch-sketch/ads-veris-analytics-platform/actions/runs/38824606157)
tested commit `1cb9824`, ten synthetic accounts and 4,000 sales rows per workbook.
The four sheets were standardized, cleaned and persisted before sustained load.
Each subsequent query changed its date filter and checked independent revenue
and related-product cost totals.

| Measurement | Result |
| --- | ---: |
| Sustained window | 600.752 s |
| Submitted / completed analyses | 590 / 590 |
| Observed end-to-end median / p95 / maximum | 2.539 / 7.964 / 16.943 s |
| Queue wait p95 | 6.713 s |
| Processing p95 | 0.896 s |
| Four-sheet standardization median | 1.613 s |
| Four-sheet cleaning median | 1.609 s |
| API peak RSS | 213.71 MiB |
| Highest individual worker RSS | 206.47 MiB |

The runner had four CPUs and local database/Storage, with separate API and worker
processes. RSS figures are per process, not total infrastructure memory. There
was at most one running heavy job, despite two consumers. Offered load was one
outstanding query per account and at least ten seconds between submissions;
this was not a saturation or maximum-capacity test. No production request or
customer file was used. These figures do not certify ten simultaneous commercial
users on Render's current resource allocation.

The run also verified API restart, recovery after a worker was killed (122.584 s,
including a real 120-second lease expiry), per-account admission limits,
cross-account denial and transient/lost-reply persistence recovery. There were
no recorded restore RPC errors after the schema correction. The separate
PostgreSQL security run `38824593336` passed the 128 concurrent snapshot writes,
in groups of eight, and preserved the owner/revision/private-RPC guards.

## Recovery drill

The disposable Supabase drill now restores two active synthetic accounts and
checks their isolation in both directions, not only anonymous access. It verifies
dataset metadata, password login, original CSV bytes and a 1 MiB binary object.
A third account erased after the backup must remain erased after restoration.
The encrypted backup and independent erasure ledger retain integrity checks.

The expanded drill passed in runs `38823403082` and `38824593406`. It restored the
CSV and binary object, preserved both accounts' password access and isolation,
and did not recreate the account erased after the backup. These small synthetic
restoration timings are deliberately not used as a production recovery promise.

The drill uses fresh loopback-only infrastructure. It is not a backup of the live
project and does not establish a production RTO/RPO. Provider settings and root
encryption keys are outside this logical restore. Supabase's own database backups
also do not include Storage object contents:
https://supabase.com/docs/guides/platform/backups

## Operational gates still required

- Select and configure an independent encrypted backup destination and a separate
  erasure ledger, with secrets provided through the operator environment.
- Back up the real deployment and restore into an approved isolated destination;
  record completeness, time, access checks and a recovery cutover procedure.
- Measure a representative workload on the intended resource budget. Local or
  GitHub-runner results do not certify commercial concurrency on Render.
- Continue profiling loading, cleaning and uncached business calculations. The
  catalog improvement does not eliminate every first-calculation delay.

No production stress test, destructive production restore or paid-service
purchase was performed as part of these changes.
