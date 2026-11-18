# Capacity and repeated-key checkpoint

## Isolated capacity lab

Run 44276258037 passed on commit 2824cae9e631ffe36c530abf74e2084017d60e61.
The previous run stopped before measuring anything because port 54322 was occupied.
PR90 assigns distinct available host ports to a disposable run directory, using
TOML parsing and rejecting paths outside that directory. It does not stop other
processes or change production. Ports are released before Docker starts; a new
external claimant can still cause a safe startup failure rather than being killed.

This run used a four-CPU CI runner, five synthetic accounts, four-sheet XLSX files
with 4,000 sales rows each and related product costs. In 120.496 seconds it completed
60/60 analyses (29.877/minute). End-to-end median/p95: 4.077/6.395 seconds;
queue p95: 4.625 seconds; processing p95: 2.286 seconds.

All 13 checks passed: ownership, authentication, private RPC denial, quota
admission, idempotency, cancellation, API restart, worker crash recovery,
four-sheet cleaning/persistence, transient snapshot failures, totals and the
global single-running-job limit across two consumers. Crash recovery took
124.003 seconds on attempt two and retained the correct total.

Simultaneous sampled API/worker RSS peaked at 591.02 MiB. This excludes database,
Storage and load-driver memory, and may double-count shared pages. There were
zero production requests and zero customer files read. These numbers do not
certify a Render plan, production concurrency or a commercial SLA.

## Repeated textual business identifiers

Profiling the owner's local relational test workbook with prepared frames showed
repeated scalar key normalization among analysis costs. The optimized `_keys`
uses existing unique-value mapping only for textual columns. Mixed numeric and
boolean values retain the original path to avoid equality collisions such as
True == 1. No cross-request cache or customer-data persistence was introduced.

Validation includes 300 generated Unicode/missing-value examples with repeated
values, nullable strings, equivalent normalized IDs, mixed booleans/numbers and
source nonmutation. The reference is the original `series.map(_text_key)`.

A five-repeat synthetic benchmark (100,000 rows, 300 distinct textual IDs) gave
median 0.34086 s scalar vs 0.01423 s unique mapping, with equal Series outputs.
This is a single-column microbenchmark, not whole-platform acceleration.

For ADS_Veris_PYME_Relacional_Pruebas.xlsx, one local paired relationship run
after preparation gave 4.3630 s scalar and 4.0103 s optimized. Complete response
hashes matched: 843d5d3e614da2fb9d66051d7ad0e100b9393f1cc936a993b7ca93dc9ba68521.
Both found 10 safe relations. Networking was blocked; no files were uploaded.
The full test suite was running concurrently, so these timings are observations,
not a controlled benchmark or a stable speedup guarantee.

## Publication and outstanding checks

PR89 was published to Render and Vercel as 20416b04fb3813cb0bf5e57e4502e39123cea0e3.
PR90 passed CI and was merged. PR91 separately fixes short signup-email followups
incorrectly routed to missing-file help; 691 assistant tests passed locally.
Publication receipts for subsequent changes belong on their pull requests.

Supabase Confirm email was enabled and the dashboard acknowledged the update.
The owner reported no message, but the focused Auth logs and account timestamps
queried then showed no new signup after activation. End-to-end signup delivery,
link confirmation and first login remain unverified, deferred until the end at
the owner's request. Recovery receipt was confirmed previously. External disaster
backup remains deferred; synthetic recovery is not a production backup.
