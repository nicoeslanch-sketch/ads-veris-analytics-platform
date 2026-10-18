# Commercial operations hardening

Scope: requested technical work before paying for services. External backups and
production restoration (point 8) are explicitly excluded. Payments and paid AI
remain disabled. This is not a promise of universal spreadsheet compatibility,
unlimited capacity, legal certification or perfect security.

## Implementation

- Single-sheet XLSX exports stream rows and avoid two redundant dataframe copies.
  Numeric types, leading-zero IDs, annotations and the audit sheet remain covered
  by regression tests. Untrusted headers and metadata cannot become Excel formulas.
- Retention lists paginated inventories, fails closed on missing profiles or
  ambiguous inventory, protects recently changed objects, and keeps an owner-scoped
  durable journal when Storage succeeds but dataset unlinking fails.
- Per-owner SQL leases prevent duplicate retention workers. Each run handles at
  most 100 expiry candidates; recent files and unknown timestamps stay protected.
- Scheduled retention reviews at most five accounts per hour across instances.
  Default `RETENTION_SCHEDULE_MODE=audit` only reports candidates. `apply` requires
  explicit operator approval. This expires originals, not all analytical snapshots.
  The existing on-upload policy remains separate and unchanged in its limits.
  Terminal journal metadata expires after 30 days in bounded batches; pending
  recovery entries are retained. This does not delete customer files.
- Optional signed HTTPS alerts contain fixed codes and aggregate state, never
  customer content. PostgreSQL coalesces states, leases delivery, fences late ACKs
  and retries failures with backoff. Receivers deduplicate `event_id` and verify
  `X-ADS-Signature` against the exact body. Delivery is at least once, not exactly once.
- The administration panel distinguishes informational retention from automatic
  expiry and configured notifications from confirmed receipt.

## Configuration still requiring an operator

The owner selected email to `servicios@adsveris.com` and audit-only inactive-account
retention. Public MX lookup on October 18 points to `smtp.google.com`; this identifies
Google routing but does not prove mailbox ownership or active sending permission.
The Gmail HTTPS adapter is prepared, not activated: use a Google OAuth client and
an owner-approved refresh token with only `https://www.googleapis.com/auth/gmail.send`.
Set `OPERATIONS_EMAIL_FROM`, `OPERATIONS_GMAIL_CLIENT_ID`,
`OPERATIONS_GMAIL_CLIENT_SECRET`, and `OPERATIONS_GMAIL_REFRESH_TOKEN` in protected
server configuration. The mailbox owner must authorize this separately; no inbox
password or inbox-reading permission is needed. Default recipient is the selected
address. Gmail takes priority over the optional webhook if both are configured.
Gmail acceptance is not delivery/read confirmation. Lost acknowledgements can
cause duplicates despite a stable Message-ID; do not promise exactly-once email.
Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send

`OPERATIONS_WEBHOOK_URL`: an existing public HTTPS endpoint on port 443, no URL
credentials, fragment or redirects. `OPERATIONS_WEBHOOK_SECRET`: a random secret
at least 32 characters, entered only in server environment and receiver settings.
Never place the secret in Git or chat. No destination has been provisioned or paid.
The sender needs a live API and database: a total service/database outage still
requires an independent external uptime monitor. A configured URL is not evidence
of receipt; perform a synthetic delivery and recovery before calling it operational.

`RETENTION_SCHEDULE_MODE`: `off`, `audit` (default), or `apply`. Do not enable apply
without approving the published policy and considering postponed external backups.
The panel shows only the last batch, not a claim that every account was checked.
On a sleeping free service this in-process scheduler pauses; it resumes on wake.
It is not an independent always-on scheduler or uptime monitor.

## Verification Checklist

- [x] Focused unit tests: export types/formula safety, retention recovery and
  ownership, webhook signing, destination restrictions, safe error reporting.
- [x] Full backend/frontend regression suites and desktop/mobile browser checks.
- [x] Disposable PostgreSQL/Storage tests: privileges, concurrent claims,
  retry fences, expiry, protected recent file, retained history.
- [x] New sustained capacity lab report with synthetic users and XLSX business view.
- [x] Before/after export measurements in fresh processes on identical input.
- [x] Additive migration `20261018232928` applied; all four new private tables
  have RLS and deny client reads; all four new RPCs deny client execution.
- [ ] Final protected PR checks and backend/frontend deployment identity.

## Boundaries of Commercial Readiness

Synthetic cached single-sheet export, 20,000 rows x 12 columns, local Windows:
4.620 -> 3.806 seconds; peak RSS 223.05 -> 155.95 MiB; additional RSS during
export 90.35 -> 25.08 MiB. One run per revision, not statistical p95 or a Render
claim. Both output workbooks were reopened and all 20,000 rows verified. Reproduce
with `python scripts/benchmark_export_streaming.py --rows 20000`.

[Capacity run 39122495283](https://github.com/nicoeslanch-sketch/ads-veris-analytics-platform/actions/runs/39122495283)
tested commit `96ac14e`, 10 synthetic accounts, 10,000 rows per four-sheet XLSX,
business joins and changing date filters, on four CPUs with local Supabase and
separate processes. 399/399 analyses completed in 613.182 seconds, 39.042/minute;
end-to-end median 14.620 s, p95 16.187 s, maximum 26.199 s. Queue wait p95 was
14.162 s, processing p95 1.569 s. API peak RSS 202.87 MiB, worker 263.07 MiB
(per-process, not total infrastructure). One outstanding request/account and at
least ten seconds between starts; not a saturation benchmark. Correct income and
related costs were checked independently for every completed job. API restart,
worker loss, persistence retries and tenant isolation passed. Worker recovery
took 123.632 s including lease expiry. Zero production requests/customer files.

The private relational fixture was rerun locally with its independent oracle:
259/259 global, period and branch checks passed; all eight available manual
relationship dashboards returned results. Fixture contents stay outside Git.
CI at `8b94890`: 2,141 backend tests and 257 frontend unit tests passed;
59 browser tests passed and one was skipped. Monitoring screenshots and overflow
checks passed at 320, 390 and 1280 px. These checks do not substitute for real
mail delivery or tests on a customer's device.

Existing tests cover registration/recovery UI, optional customer MFA, plan expiry,
atomic coins, cleaning, relational totals, period selection, downloads, history,
and account/dataset deletion sagas. Re-run them, do not replace them with a manual
happy-path claim. Production email delivery and customer-device behavior are
separate checks; synthetic load is not a certified Render user limit.

The accepted input contract, not marketing language, determines compatibility:
supported XLSX/CSV files and supported Google Sheets tab imports;
invalid formulas, ambiguous currencies and joins must remain visible as limitations.
No plan price, coin value, paid provider or user-company authorization model is
changed in this release. Existing commercial catalog/entitlement tests remain gates.

Security Advisor was reviewed on October 18. Backend-only private tables have RLS
with no client policies intentionally; client privileges are separately revoked.
The existing `can_process_data()` warning was inspected: it returns only the
authenticated user's commercial eligibility and is used by existing RLS policies.
It was not blindly revoked or changed in this maintenance release. Leaked-password
protection remains an operator/provider configuration item, not a completed feature.
References: [function advisor](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable),
[password protection](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection).
