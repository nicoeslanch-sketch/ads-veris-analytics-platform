# Security review - 2026-11-04

## Scope and boundaries

Source review, bounded synthetic tests and read-only production metadata review.
No customer files were downloaded, no production attack/load campaign was run,
and no paid services, payment processing or AI provider were enabled.
This is not a penetration-test certification or a guarantee against compromise.

## Verified production metadata

- All 30 public application tables and 12 app_private tables have RLS enabled.
- Dataset storage is private. Owner-folder policies and restrictive MFA/session
  guards apply. Direct client writes are blocked in favor of managed uploads.
- anon/authenticated have no table DML privileges in app_private.
- Profile client updates cannot modify plan, administrator status or credits.
- The only public SECURITY DEFINER callable by authenticated is the intentional
  no-argument can_process_data() policy helper. Privileged RPCs are service-only.
- No client-readable public views were found. Google Sheet links have a composite
  ownership constraint in addition to backend ownership validation.
- Auth settings report mailer_autoconfirm=true: email ownership is NOT currently
  verified on signup. Do not confuse operational Gmail delivery with Auth mail.

## Changes in this review

- Managed uploads validate actual CSV/XLSX content before persistence. Reject
  binary masquerading as CSV, invalid workbooks, macros/ActiveX, duplicate or
  encrypted ZIP entries, unsafe paths, excessive entry counts and XML entities
  in workbook content-type metadata. Existing expansion/size limits remain.
- Production uploads use the existing distributed request budget: 20 per minute
  per account, in addition to storage quotas and concurrent processing admission.
- Unsafe production CORS origin values and common overly broad regex patterns
  prevent startup. This is a guardrail, not proof that every regex is safe.
- AI failures log incident IDs and exception types, not provider bodies, prompts,
  credentials or account IDs. Denied CORS origins/paths are not echoed in logs.
- CSV report text neutralizes formula prefixes including leading whitespace and
  control characters, and correctly quotes carriage returns.
- Regression tests enforce backend authentication on private API routes and
  exercise malformed uploads, preserved valid uploads, rate budgets and logs.
- Disposable PostgreSQL tests now enforce schema-wide RLS, private grants,
  privileged RPC allowlists, protected profile columns and private storage.

## Advice evaluated rather than copied

- Authorization belongs in the backend and database, not just UI visibility.
  Existing JWT/live-session checks, ownership scoping and RLS are retained.
- A publishable Supabase key in a SPA is not a service_role secret. Browser keys
  must remain constrained by RLS and privileges. service_role stays backend-only.
- UUIDs alone are not authorization. Existing ownership and cross-owner link
  tests remain mandatory. SQL string concatenation in the disposable lab uses
  internally generated UUIDs, not end-user queries.
- Customer passwords are handled by Supabase Auth, not stored by this app.
- Customer MFA remains optional; administrator MFA remains mandatory.
- No payment webhook is enabled. Enabling purchases remains blocked until a
  provider integration with verified signatures and idempotency is tested.
- Blue branding is retained. No visual redesign is required for security.

## Residual work / limitations

1. Verify Auth email delivery and then enable signup confirmation. The dashboard
   session was established, but browser access became disabled while checking
   SMTP. No mail settings were changed and no delivery success is claimed.
2. Breached-password protection is disabled in production. Confirm plan support
   and backend password policy before enabling; do not purchase an upgrade.
3. The SPA uses Supabase's persisted browser sessions (localStorage). CSP,
   escaped rendering and dependency review reduce XSS risk but do not eliminate
   token theft after successful same-origin script injection. HttpOnly sessions
   require a coordinated backend-for-frontend/CSRF design, not a storage toggle.
4. Body limits/timeouts and heavy-work admission exist; a global pre-auth body
   receive admission limit and infrastructure-level abuse controls need further
   review. Distributed upload quotas do not prevent all network exhaustion.
5. Existing service_role use still requires ownership scoping on every backend
   access. Schema and route inventory tests complement, not replace, code review.
6. External disaster backups and sustained commercial capacity certification
   remain separate, previously deferred work. Retention stays review-only.

## Local verification

- Backend: 2,273 tests passed (131 existing deprecation/runtime warnings), followed
  by 31 focused review tests including four additional encoding/CSV regressions.
- Frontend: 267 tests passed; production build succeeded.
- npm audit policy passed. CI dependency and tracked-history secret scans passed.
- Disposable PostgreSQL run 41928084898 passed all 39 checks, including tenant
  isolation, revoked sessions, protected roles and transaction rollback. It made
  zero production requests and accessed zero customer files.
- Restore lab run 41928085278 passed. This is a synthetic recovery drill, NOT a
  production disaster backup. Repeat PR checks on the final commit before merge.
- pip-audit was not installed locally; the dependency audit ran in CI instead.
