# Adaptive exploration and product evidence

## Scope

Engine 0.35.0 adds bounded product histories and conservative recurring-peak
evidence. It does not change cleaning rules, remove duplicates, convert currencies,
activate paid AI or perform business decisions automatically.

Explorar differs from Resumen in all three presentation paths:

- Ordinary single-sheet or consolidated metrics retain two overview charts and
  brief decisions, plus a grouped analysis selector.
- Reconciled multi-sheet ledgers show an evidence/decision workspace instead of
  repeating the summary KPI strip and dashboard tabs.
- Manual relationships show one selected comparison, up to three findings/alerts
  and expandable indicators. Their query and ownership validation are unchanged.

## View catalog

Only eligible views are displayed. They are grouped under Evolution, Composition,
Products and Operations; one additional view renders at a time.

| View | Evidence requirement / guard |
| --- | --- |
| Sales, cost and profit trend | Reconciled ledger movements |
| Same month across years | At least two non-partial observations of the same month |
| Consecutive monthly change | Adjacent complete months; absolute change, rates in percentage points |
| Product revenue ranking | Reconciled product revenue, not units or margin |
| Revenue concentration / Pareto | Nonnegative groups reconcile to the total; remainder preserved as Other |
| Segment-month heatmap | Matching dimension and month, missing cell remains null |
| Product revenue versus profit scatter | Same-grain product amounts with full matched-cost coverage |
| Months without observed positive sales | Existing backend ID-based inactivity evidence |
| Capital in slow inventory | Reconciled stock at cutoff and latest observed sale |
| Weekday activity | Transactional sales only; accumulated, not daily average |
| Result drivers | All reconciled components present; total not an additional component |
| Operational balances | At least two observed balances at cutoff, not period flows |
| Product calendar | Stable product ID and dated amounts, not inferred from top rankings |
| Recurring annual peak | Same peak month in multiple comparable years, see below |

Existing summary visualizations and domain-specific measures for collections,
services, inventory, campaigns and generic sheets remain available. No fake funnel,
forecast, histogram or percentage distribution is generated without its necessary
source data. A limited chart catalog cannot describe every possible spreadsheet.

## Product methodology and limits

- Uses all valid dated product IDs to detect patterns before truncating presentation.
- Net monthly values retain returns. Positive-sales concentration excludes returns.
- Comparable years require all 12 observed months and non-partial source boundaries.
  Unknown-date positive sales disqualify the affected product from peak conclusions.
- Same unique peak month must account for at least 30% of positive sales in each
  of at least two comparable years (last five eligible years at most).
- This is a disclosed screening heuristic, not a statistical seasonality test,
  causal explanation, forecast or proof of complete business coverage.
- Up to eight peak findings and twelve product series; up to 36 source months and
  18 heatmap columns. Exact values remain available in the displayed view.
- Legacy multi-sheet aggregates do not reuse a single sheet's product history as
  if it described the whole business. Reconciled ledgers have their own histories.
- Decisions ask the customer to verify stock, margin, coverage, season and
  marketing. They never automatically recommend dropping a product from a ranking.

## Bot and quality vocabulary

Seasonal questions and follow-ups use the same aggregates as the UI, retain
product/month context and decline unknown products, unsupported years and forecasts.
Added deterministic explanations for IDs with leading zeros, missing versus zero,
outliers, numeric separators, chart selection and cleaning versus standardization.
Joined words and controlled typo correction cover the added vocabulary.
No external model call or ADS Coin charge was introduced.

## Verification

- Full backend suite: 2,097 passed. Frontend production build and type check passed.
- Reproducible multi-turn conversation, typos, unknown products, future years,
  malformed context, returns, missing months, single-year and ID separation tests.
- Frontend eligibility tests cover incomplete Pareto denominators, negative groups,
  rates, partial dates, missing cells, cost coverage and changing period scope.
- Playwright checks every offered chart in synthetic single-sheet and reconciled
  contexts at 1440, 390 and 320 pixels; screenshots, rendered marks, selection,
  exact values, currency and text overflow are checked.
- Full application browser suite: 59 passed, one optional private-file test skipped.
  The manual-relationship explore path was additionally exercised after its update.
- The supplied private relational workbook is checked locally against its oracle:
  259/259 numerical checks, automatic detail-based business scope and all offered
  manual dashboards passed. Neither workbook nor oracle is committed.
- Local helper benchmark: 200,000 rows, 5,000 product IDs, 2.144 seconds, 16,115-byte
  response. This is not an end-to-end production latency or capacity guarantee.

The audit CLI must focus on the transactional detail sheet (DET_VENTAS in this
fixture), not its document header. Diagnostic failures now identify missing or
different metrics instead of returning only an undifferentiated comparison error.
