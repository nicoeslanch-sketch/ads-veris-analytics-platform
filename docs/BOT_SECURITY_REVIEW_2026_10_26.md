# Bot and defensive review, 2026-10-26

## Scope and evidence

Five user screenshots exposed reproducible answer-routing errors. The initial
suite had 20 failures out of 21 synthetic variants. No customer workbook or private
conversation was copied into the repository. Synthetic numbers reproduce the
failure modes; they do not certify the source spreadsheet's financial totals.

## Corrections

- Platform-purpose questions no longer select the capacity article.
- Worst-category questions use the lowest published income, not the leader.
  Rankings explicitly describe the published groups, which can be a truncated top.
- Requests to add several named groups include all selected groups. Missing group
  names prevent a silently partial sum; mixed currencies are not combined.
- Requests for distinct KPIs, such as units versus operating profit, answer both
  and carry explicit period/segment constraints into the component questions.
- A segment's best/worst month never uses the overall monthly total. A compatible
  published month/dimension matrix can answer the ranking, excluding partial
  months; without that evidence the bot explains the missing cross-tabulation.
- Signed single-sheet quantities now expose positive/negative sums, missing
  quantities, and positive quantities paired with negative amounts. The bot
  distinguishes these from the relational ledger's units before returns.
- Gross profit, operating result and pre-tax result are not relabelled as one
  another when the requested measure is absent.
- Topic changes, human support and follow-up rankings have regression cases.
- Mobile chat resets the input's scroll offset after sending, keeping the start
  of the placeholder visible after a long question.

Engine version: `0.36.1`; no database migration or paid service activation.
Cached older contexts retain a cautious explanation when quantity detail is absent.

## Performance and safety

- High-confidence built-in support answers no longer read the remote catalog.
- Catalog reads never seed/update the database. The optional read timeout is
  reduced to 3 seconds. Concurrent readers use cached or built-in articles instead
  of waiting on a global lock held throughout a remote request.
- A deterministic concurrency test blocks the loader and confirms another caller
  receives the local fallback without waiting for that network operation.
- Metric context rejects non-finite numbers, overlong strings/keys and malformed
  quantity metadata in addition to the existing depth/node/body limits.
- Uploads have a 120-second total body-receive deadline plus the existing
  30-second idle limit. Sending small chunks cannot extend the upload indefinitely.
  This bounds network reception, not spreadsheet calculation time.

Local conversation exercise: 202 turns, 0 failed expectations, median 4.950 ms,
p95 16.260 ms, maximum 48.806 ms. These are in-process synthetic answer timings,
not production HTTP latency or a concurrent-user capacity guarantee.

## PHP advisory applicability

The official PHP notice of October 21 covers CVE-2026-109618 and
CVE-2026-109619; the October 23 note discusses CVE-2026-115560. See the
[PHP security notices](https://www.php.net/archive/2026.php).

The tracked application has no PHP/Composer files or PHP server runtime. Its API
is Python/FastAPI and its frontend is React/Vite, so no directly affected PHP
component was identified in ADS Veris. This is an applicability assessment, not
proof that third-party infrastructure has never been compromised. Provider-owned
hosts and incident logs were not inspected, and no exploit traffic was sent.

## Verification

- Full local API suite: 2240 passed before six additional follow-up regressions.
- Frontend unit suite: 257 passed; production build and type checking successful.
- Browser bot suite: 6 passed, including real local API answers, context changes,
  desktop/mobile continuity and overflow assertions; screenshot inspected.
- `scripts/exercise_assistant.py`: 202 turns, zero expectation failures.
- `pip-audit -r api/requirements.txt`: no known vulnerabilities reported.
- Frontend audit: no applicable high/critical findings under the existing policy.
- Gitleaks: 331 historical commits, no exposed secrets detected, redacted output.
- Production `/version` before release: HTTP 200, commit `cd33b38`, engine `0.36.0`.
  A preceding cold `/health` request timed out; this release does not eliminate
  free-tier cold starts or establish commercial capacity.

Required CI checks, including the isolated PostgreSQL authorization/concurrency
suite, must pass before merging. Production verification is separate from local
tests. Payments, paid AI, automatic inactive-account deletion and external backup
provisioning remain unchanged and disabled/deferred as previously instructed.
