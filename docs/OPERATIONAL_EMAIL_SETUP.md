# Owner-approved operational email

This connection sends content-free operational alerts. It does not read the
inbox, send marketing, reset customer passwords, activate billing or run paid AI.
Customer email delivery from Supabase Auth is a separate configuration.

## Authorize

1. Enable Gmail API in the owner's Google project. Prefer an Internal app when
   the sender belongs to the same Workspace organization. An External app in
   Testing can issue refresh tokens that expire after seven days for Gmail scopes.
2. Create a Desktop OAuth client. The owner accepts legal terms and grants only
   `https://www.googleapis.com/auth/gmail.send`. No inbox-reading scope is needed.
3. Place its JSON as `client.json` in an owner-only directory outside any Git
   checkout or shared/synced folder. On Windows remove inherited ACLs and grant
   only the owner access; on POSIX use mode 0700. Never paste secrets into chat.
4. Install the optional workstation tool with
   `python -m pip install -r scripts/requirements-mail-setup.txt`. This dependency
   is not installed in the production API.
5. Run `python scripts/authorize_operational_email.py --private-directory <private-directory> --authorize`.
   The Google library uses PKCE, state validation and an ephemeral loopback port.
   The authorization URL is written privately, not printed. The owner opens it
   and completes consent within 30 minutes (bounded `--wait-seconds` is available).
6. A successful run writes `render-email.json` privately. An expired run does not
   create that file. Stop the old process before renaming its expired
   `authorization-url.txt` and retrying. Never reuse a callback or authorization
   code, overwrite a working credential, or share either output file.
7. Merge the five named values into the intended Render service's protected
   environment, preserving every unrelated variable. Do not put values in
   `render.yaml`, GitHub Actions, a frontend build, logs or this document:
   `OPERATIONS_EMAIL_TO`, `OPERATIONS_EMAIL_FROM`, `OPERATIONS_GMAIL_CLIENT_ID`,
   `OPERATIONS_GMAIL_CLIENT_SECRET`, `OPERATIONS_GMAIL_REFRESH_TOKEN`.
8. Confirm the resulting deploy is live and healthy. A saved environment change
   alone does not prove that a running process has loaded it.

## Test and Operate

`python scripts/check_operational_email.py` reads only process environment (not
`.env`) and never sends. Add `--send-test` only with owner approval to send exactly
one synthetic message. It does not mutate real alert state or retry automatically.
No secrets are printed, including on exceptions. Run in the deployed environment
when available; a workstation test proves provider acceptance but not delivery
from the deployed runtime. The owner separately confirms inbox/spam receipt.

The production adapter rejects invalid token replies and any explicit grant
broader than send-only. Fixed HTTPS endpoints, bounded timeouts and disabled
redirects/proxies protect the credential exchange. Alert content includes only
fixed codes, UTC time and an opaque reference, never customer files or records.
The existing PostgreSQL queue leases delivery and retries failures with backoff.
Lost acknowledgements can cause duplicate emails; Message-ID is not an
exactly-once guarantee. Do not repeatedly send tests to troubleshoot a lost reply.

To revoke, the owner removes the app's access in Google Account security and
removes the email credentials from Render before redeploying. Preserve any
separately configured webhook. Rotating the client secret alone is not proof
that all previously issued access or refresh tokens have been revoked.

This sender depends on the API and database being available. It cannot report
its own complete outage. Free-service sleeping also pauses the in-process
scheduler; independent uptime checks remain necessary. Retention stays in audit
mode, with no automatic inactive-account file deletion. External backup work
remains explicitly deferred.

## Capacity Measurement

`benchmark_durable_local.py` now samples all owned live API and worker processes
together. `aggregate_process_resources.peak_sum_rss_mib` is the maximum sum in
one complete sample, not the sum of unrelated per-process peaks. Failed process
reads are counted separately and never treated as complete observations. This
RSS sum excludes PostgreSQL, Storage and the load driver, can double-count shared
pages, and is not total host physical memory. It is not a production user limit.

## Activation Evidence (2026-10-20)

- The owner granted send-only access. Protected Render variables were merged,
  preserving other settings, and the resulting deployment became live.
- The single workstation test was accepted by Google and the owner confirmed
  receipt. No inbox-reading permission was used to verify it.
- Independently, the deployed operational monitor emitted `RETENTION_PENDING`.
  Its database delivery revision was acknowledged with zero failures and no
  outstanding lease. This verifies provider acceptance from the deployed API,
  without pretending to confirm reading of that separate alert.
- Public API health returned OK. Inactive-account retention stays audit-only.
- The reproducible bot audit passed all 192 synthetic conversation turns.
- The new dependency gate found Vite advisories published that same day. The
  frontend minimum is raised to the compatible patched 6.4.4 release, without
  suppressing the advisories or upgrading to a new major version.

## References

- [Google OAuth for installed apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Refresh-token expiration](https://developers.google.com/identity/protocols/oauth2#expiration)
- [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Render environment variables](https://render.com/docs/configure-environment-variables)
