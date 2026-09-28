# Release 0.32.5

## Inventory snapshot interpretation

- Recognize StockUnidades and spaced/underscored variants without confusing
  the letters `id` inside `unidades` with an identifier column.
- Continue excluding actual identifier columns such as IDStock.
- Prefer the unit reference cost declared in the inventory snapshot. Only
  use the validated product catalog when the snapshot has no unit-cost column.
- Retain the latest global snapshot rule; do not add monthly inventory balances.
- Publish valuation coverage and mark incomplete valuations as partial. Missing
  costs are not filled from another source when a snapshot cost column exists.
- Missing stock minimums are unavailable, not zero shortages.
- The assistant carries partial valuation warnings into its answer.

The engine version invalidates earlier analytical caches. Cleaning decisions,
source files and the user's duplicate-retention choices are unchanged. No new
database migration, payment activation or infrastructure subscription is required.

## Verification

Synthetic regressions cover header variants, misleading numeric identifiers,
different catalog and snapshot costs, multiple dates, missing costs and missing
stock quantities. A private workbook comparison is kept outside the public repo.

## Assistant and download verification follow-up

- Recognize conversational questions about whether inventory or receivables
  represent money available to spend. Explain the cash/bank inputs needed
  without presenting stock value or customer debt as spendable cash.
- Preserve spending vocabulary and support the observed joined-word variant.
- Reopen the browser-downloaded synthetic workbook in E2E, checking required
  sheets, row counts, quantities and sales sums rather than only its filename.

This follow-up changes no analytical formula or cache version. Payments remain off.
