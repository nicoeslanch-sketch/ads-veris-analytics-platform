# Experience and performance follow-up, 2026-11-16

## Scope and decisions

- User approved values-only workbook assembly, not formula preservation.
- No paid services, payment activation, AI activation, retention deletion or customer-data downloads.
- Registration email confirmation is deferred to the end at the user's request.
- Root checkout and unrelated generated demo JSON changes are left untouched.

## Implemented in this branch

- Responsive shimmer skeletons for dashboard, table and form loading; reduced-motion
  support, accessible status, elapsed time and existing cancel actions preserved.
- Removed duplicate profile/settings menu destination. One Settings entry remains.
- Restrained categorical colors with stable category assignment, distinct financial
  series, explicit negative-value warning color. Ledger money uses the shared formatter
  (including UF precision) instead of an independent two-decimal formatter.
- Replaced the public advanced consolidation wizard with a simple multi-XLSX download.
  The advanced backend remains intact for compatibility; this new flow does not run it.
  Limits: 2-10 files, 15 MiB total, 100 sheets, 500,000 bounding-grid cells,
  200,000 rows/300 columns per sheet, 100 MiB expanded ZIP, 8 MiB per non-sheet part.
  Existing JWT/feature/admin access and heavy-work admission remain enforced.
  Names are unique case-insensitively within Excel's 31-character limit; all rows and
  duplicates remain. Dates/number formats and cached results are retained, not design,
  charts or formulas. Missing formula caches fail the whole operation explicitly.
  Text starting with '=' remains text. No durable new source/dataset is created.
- Warm manifest preparation checks the exact pipeline cache before network reads or
  reopening XLSX. Clean artifact persistence is retained, and already-persisted memory
  identities skip repeated uploads. Tests vary revision, source, dataset, rules,
  mapping, scope and duplicate settings to reject stale reuse.
- Additional bounded timing stages identify workbook opening, cleaning and artifact
  persistence without logging file contents or account metadata.
- Bot now distinguishes workbook assembly from sales-period consolidation, handles
  related follow-up questions, explains loading placeholders and connection waits.
  Valid words such as 'varios' and 'relaciones' no longer become 'vacios' or 'relacion es'.
- RapidFuzz 3.14.6 replaces the bounded edit-distance primitive only. Controlled
  vocabulary, ambiguity policy and thresholds remain; no external model or API.
  Upstream MIT license: https://github.com/rapidfuzz/RapidFuzz
  SymSpell was not added: no demonstrated need for an additional dictionary/segmenter.
- Local bot-evaluation skill now includes assembly-vs-join, plural preservation and
  semantic-parity/performance checks for fuzzy libraries. This skill is local, not deployed.

## Observed performance, not an SLA

Read-only Render log from 2026-11-16 22:56:50 UTC recorded a relationships job:
145,686.5 ms total, prepare_sheets 107,061.8 ms (including 23 restore calls totalling
15,627.3 ms), compute_metrics 18,756.7 ms. Nested stages must not be summed.
This is consistent with the reported 151-second UI wait, but not proof of the exact
same browser request. It demonstrates substantial server-side work beyond cold startup.
Following jobs restored the same sheet count in about 43-101 ms. No before/after
production speedup has been certified for this branch.

Local normalization benchmark: 300 synthetic vocabulary typos, cleared caches before
each run, 466.47 ms old primitive / 29.15 ms RapidFuzz, identical outputs. This measures
normalization only, not overall bot response or dashboard latency. Reference-distance
tests check 2,000 seeded comparisons with cutoffs.

## Authentication and privacy evidence

- Code review: registration requires LegalConsent and records service_data_consent
  plus legal_version. Settings/PrivacyCenter is a separate rights/data-management view.
- Live public Auth settings on 2026-11-16: signup enabled, email enabled,
  mailer_autoconfirm=true. Thus email confirmation is NOT currently required.
- One recovery request for the owner's existing servicios@adsveris.com account returned
  HTTP 200; user independently confirmed receipt. No password was changed and no link
  or credentials were collected. This proves this delivery only, not delivery to all
  customer domains or the complete reset-password flow.
- Browser control became unavailable in this chat, even after the user opened Supabase.
  Live confirmation/SMTP settings were not changed. Check custom SMTP/send-hook coverage,
  then enable and verify new-account confirmation at the end. Do not claim it is enabled.

## Verification checkpoint

- Frontend build passed; 293 Vitest tests passed.
- Backend full run: 2,354 tests passed; then 44 focused tests passed including the four
  added endpoint access/download cases and latest persistence adjustments.
- Six focused Playwright scenarios passed, including 320/768/1440px skeletons,
  reduced motion, download UI and relational workbook cleaning, charts, periods and bot.
- Full browser suite: 65 passed, 1 private-fixture skip, 1 test timeout. Trace showed
  session-workspace's synthetic alert had the correct preserved contents, but the
  test awaited the click before dismissing its blocking dialog. Fixed the test's
  dialog synchronization; all eight targeted session/loading/menu scenarios passed.
- Dependency audit: no known vulnerabilities in Python requirements.
- PR 88 initial CI: backend, frontend, dependency checks, tracked-history secret scan,
  isolated PostgreSQL ownership/concurrency/audit rollback and synthetic encrypted
  database/Storage restore drill passed. These are not a production disaster backup.
- No production deployment of this branch yet at this checkpoint; final CI and release pending.

## Still open

1. Finish full checks, review and protected-branch publication; verify live release.
2. Re-measure cold calculations after deployment; remaining 100+ second paths need
   profiling rather than promises that a paid plan alone fixes them.
3. Broader capacity certification, future paid-AI guardrails and recovery demonstration
   remain separate work; external backup location is deferred by the user.
4. At the end: inspect SMTP/send-hook and confirm new registrations by actual email.
