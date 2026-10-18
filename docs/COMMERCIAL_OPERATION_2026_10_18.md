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

## Verification Checklist

- [x] Focused unit tests: export types/formula safety, retention recovery and
  ownership, webhook signing, destination restrictions, safe error reporting.
- [ ] Full backend/frontend regression suites and desktop/mobile browser checks.
- [ ] Disposable PostgreSQL/Storage tests: privileges, concurrent claims,
  retry fences, expiry, protected recent file, retained history.
- [ ] New sustained capacity lab report with synthetic users and XLSX business view.
- [ ] Before/after export measurements in fresh processes on identical input.
- [ ] Protected PR checks, additive migration, backend/frontend deployment identity.

## Boundaries of Commercial Readiness

Existing tests cover registration/recovery UI, optional customer MFA, plan expiry,
atomic coins, cleaning, relational totals, period selection, downloads, history,
and account/dataset deletion sagas. Re-run them, do not replace them with a manual
happy-path claim. Production email delivery and customer-device behavior are
separate checks; synthetic load is not a certified Render user limit.

The accepted input contract, not marketing language, determines compatibility:
supported XLSX/CSV/text-delimited formats and supported Google Sheets imports;
invalid formulas, ambiguous currencies and joins must remain visible as limitations.
No plan price, coin value, paid provider or user-company authorization model is
changed in this release. Existing commercial catalog/entitlement tests remain gates.
