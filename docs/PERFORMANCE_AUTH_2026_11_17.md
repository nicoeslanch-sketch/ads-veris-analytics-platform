# Performance and registration checkpoint

## Delivered in this change

- ASCII normalization avoids unnecessary Unicode decomposition. Non-ASCII follows
  the original algorithm; 1,000 generated examples and explicit Unicode boundaries
  compare against the original implementation, without caching customer text.
- Offline workbook benchmark separates read/preparation and cold/warm paths,
  blocks outgoing socket connections and records hashes rather than cell values.
- Relationship telemetry separates discovery and business analysis. No account,
  filename, column or cell is added to timing labels.
- Session lookup before API calls has a 15-second bound and supports cancellation.
  Failed/late refresh never sends an unauthenticated fallback request. Ten tests
  cover GET, multipart, downloads, DELETE, JSON, PUT, streaming and late tokens.
- Security gate uses skeletons while private content remains inaccessible.
- Registration distinguishes session creation from pending email confirmation,
  clears passwords and offers signup-email resend with a 60-second UI cooldown.
  Supabase remains responsible for enforcing server-side email rate limits.
- Login/recovery network exceptions now release controls and show safe messages.
- Deterministic bot has scoped signup-confirmation help, typo/joined-word cases,
  follow-ups and negative tests distinguishing sales, password recovery and files.

## Measured evidence

User-provided relational test workbook: 22 data sheets, 16,546 processed rows.
Fresh local processes without profiler: before 14.0105 s (read 4.8169,
prepare 9.1936); after 11.4326 s (read 4.5601, prepare 6.8724).
Warm preparation + read: approximately 0.167 s in both runs. Frame/mapping/summary
hashes match exactly. This single paired observation is not a stable speedup claim,
Render benchmark, upload timing, or commercial capacity certification.

Local reconciliation against the supplied JSON oracle: 259/259 checks passed,
including global indicators, periods and branches. No files were uploaded.

Authenticated production UI on November 17 (Santiago) showed the existing test
workbook's reconciled net sales 258,743,351 CLP, gross profit 108,826,271 CLP,
result before tax -69,690,379 CLP, receivables 15,561,051 CLP. Years/months and
DET_VENTAS -> LOTES many-to-one coverage were present, with 6,210 unchanged rows.
Render timing at 2026-11-18T00:34:14Z recorded relationships 60,386.7 ms,
restore 23 sheets 14,492.7 ms, preparation 14,546.5 ms and compute 17,630.4 ms.
Stages are nested, not additive. This observation ran the previous release
f876514, not this branch. The earlier 145-second observation is not a controlled
before/after comparison. Further production latency work remains.

## Auth live state and limitations

Supabase dashboard showed custom SMTP enabled at smtp.resend.com:587, sender name
ADS Veris, correct production Site URL and recovery redirects. Credentials were
not read or changed. Confirm email was OFF. Browser access was interrupted before
activation; no setting was changed. Owner previously confirmed recovery receipt.
New signup delivery, confirmation link and first-login verification are still open.
No paid resources, payment integration or paid AI were enabled. External disaster
backup remains deferred by the owner; synthetic restore tests do not replace it.

## Verification

- Backend full run before the final bot/telemetry additions: 2,365 passed.
- Focused bot/performance/telemetry run after additions: 47 passed.
- Frontend: 303 unit tests passed; production build passed.
- Browser: 15 focused signup, MFA and session-preservation scenarios passed.
- Final CI and publication receipts are recorded on the pull request.

## Newly reviewed dependency advisory

CI on November 17 detected GHSA-fc5q-39xc-vjpf (CVE-2026-112366), updated that
day: https://github.com/advisories/GHSA-fc5q-39xc-vjpf . The advisory reports
picomatch <=4.0.7 affected and no patched release. npm registry latest is 4.0.7.
Do not apply npm's suggested force downgrade of Vite/Vitest to bypass this.

The installed picomatch 4.0.4 is used only by dev/build tools (Vite, Vitest,
tinyglobby, fdir), all marked dev=true in package-lock. No matching library
imports or user-supplied glob evaluation exist in frontend/src or scripts.
Production is static Vite output, not a Vite dev server. npm audit --omit=dev
reports zero vulnerabilities. These facts restrict reachability; they do not
patch picomatch. Build/test infrastructure must not process untrusted globs.

A narrow temporary disposition accepts only this advisory through these five
reviewed packages, only when every reported node is dev-only, and expires at
2026-11-25T00:00:00Z. New advisories, runtime nodes and expiry fail CI. Policy
tests enforce those boundaries. Recheck upstream and update/remove the disposition
when a patched release is available; no general severity threshold was lowered.
