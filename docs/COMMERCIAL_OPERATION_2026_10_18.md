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
- [ ] Full backend/frontend regression suites and desktop/mobile browser checks.
- [ ] Disposable PostgreSQL/Storage tests: privileges, concurrent claims,
  retry fences, expiry, protected recent file, retained history.
- [ ] New sustained capacity lab report with synthetic users and XLSX business view.
- [x] Before/after export measurements in fresh processes on identical input.
- [ ] Protected PR checks, additive migration, backend/frontend deployment identity.

## Boundaries of Commercial Readiness

Synthetic cached single-sheet export, 20,000 rows x 12 columns, local Windows:
4.620 -> 3.806 seconds; peak RSS 223.05 -> 155.95 MiB; additional RSS during
export 90.35 -> 25.08 MiB. One run per revision, not statistical p95 or a Render
claim. Both output workbooks were reopened and all 20,000 rows verified. Reproduce
with `python scripts/benchmark_export_streaming.py --rows 20000`.

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
