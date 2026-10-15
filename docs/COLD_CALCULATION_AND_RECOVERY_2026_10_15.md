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

The manual capacity workflow now offers `analysis=business` for its four-sheet
XLSX fixture. It consolidates three periods, joins product costs and verifies
both revenue and known cost against independent daily sums for every completed
job. `analysis=append` retains the older workload for comparison; business mode
rejects CSV rather than silently measuring a different path. Preparation,
persistence fault injection, worker-crash recovery, account isolation and the
global one-heavy-job limit remain enabled.

## Recovery drill

The disposable Supabase drill now restores two active synthetic accounts and
checks their isolation in both directions, not only anonymous access. It verifies
dataset metadata, password login, original CSV bytes and a 1 MiB binary object.
A third account erased after the backup must remain erased after restoration.
The encrypted backup and independent erasure ledger retain integrity checks.

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
