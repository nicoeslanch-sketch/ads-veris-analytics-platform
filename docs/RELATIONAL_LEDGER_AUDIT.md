# Relational workbook reconciliation (engine 0.34.0)

## Boundary and methodology

The commercial ledger is identified from column schemas, not workbook names or
control totals. Original sheets and cleaned exports are not flattened. Sales
details inherit non-monetary header attributes through a validated document ID.
Header amounts are never copied onto every line.

Sales, credit notes, returns, inventory lots, collections, refunds, purchases,
supplier payments, expenses, payroll and loans remain independent facts.
Payments are grouped before receivable/payable arithmetic. Revenue follows the
document date; credit notes follow their own date. Historical line costs are
reversed only when returned goods re-enter stock. Cash uses payment dates.
Balances include movements before the beginning of a selected period.

Conflicting primary keys, orphan references, incompatible currencies, unknown
states/dates, excessive returns, negative inventory and irreconcilable document
totals block publication of reconciled financial figures. Missing optional
sources produce unavailable indicators, not invented zeros. This is a specific
supported ledger schema, not a claim to understand arbitrary accounting models.

## Corrections

- Suffix IDs (for example `venta_id`) are identifiers, never revenue measures.
- Explicit net document/line amounts beat gross totals and unit prices.
- Credit/debit note sheets are transaction sources, not auxiliary instructions.
- Prefix and suffix customer/employee IDs can link the same entity safely.
- Manual purchase/provider queries publish supplier spending charts.
- Manual customer/seller tickets count distinct sale IDs, not product lines.
- Key-only connections without analytical variables are not offered.
- Business mode supports years/months within one sales table.
- The dashboard and deterministic bot use the reconciled ledger. Changing a
  period invalidates the bot's context; it cannot reuse a previous month's
  snapshot just because the relationship is unchanged.
- Auth bootstrap cannot overwrite a newer sign-in or sign-out event.

## Reproducible evidence

Synthetic regression fixtures live in `api/tests/test_relational_ledger.py` and
`api/tests/test_relational_semantics.py`. Bot tests include independent questions
and a 24-turn conversation with changing topics and period follow-ups.
`frontend/e2e/relational-ledger.spec.ts` exercises upload, standardization,
cleaning, year/month selection, chart rendering, navigation and five bot turns.
Layout checks cover 1280, 390 and 320 pixel viewports.

The private workbook audit can be repeated locally:

```text
python scripts/audit_relational_ledger.py <workbook.xlsx> --oracle <oracle.json> --pipeline-focus <sales-detail-sheet> --output <private-output.json>
```

It independently compares 25 global indicators, ten indicators for each of 21
months and both years, and revenue/cost for two branches: 259 checks. The actual
automatic relationship path is also checked against the reconciled values.
Every offered manual relationship is built and checked for availability; eight
useful relations in the reference workbook produce charts.
Neither the workbook nor the oracle is required by production code; they must
not be committed or uploaded to the public repository.

## Production verification (2026-10-14)

The authenticated workflow completed standardization and cleaning of 22 data
sheets, preserving 16,546 rows without requesting deduplication. The workbook
download completed, and its exported data passed the same 259 oracle checks.
Business mode rendered the reconciled figures and the 2025 filter matched the
reference. Five live bot questions covered total revenue, a year follow-up,
gross profit, product profitability and human support.

Cold calculations and full-workbook export still took minutes on the current
basic server. This is a correctness check, not a latency or capacity guarantee.
An old browser tab also failed to load a removed JavaScript module; explicit
reload restored the saved work. The recovery message now distinguishes that
interface failure from a cleaning error and warns about unsaved changes rather
than automatically reloading. Year, quarter and custom-range labels no longer
masquerade as the first month; reconciled exploration uses one period selector.

## Limits and rollout

The ledger does not infer an opening bank balance, complete balance sheet,
liquidity ratios, tax filing, causal marketing effect or arbitrary SQL results.
Manual relationships are safe joins and aggregations, not a SQL console. A
manual sales-line query is before credit notes; complete net revenue belongs
to the business ledger. Source and date boundaries remain visible.

For old uploads, confirm that credit-note sheets are selected and cleaned.
Engine-versioned caches are invalidated, but a user's deliberate sheet selection
is not silently changed. Financial correctness on this workbook does not
certify commercial concurrency, disaster recovery or every possible workbook.
