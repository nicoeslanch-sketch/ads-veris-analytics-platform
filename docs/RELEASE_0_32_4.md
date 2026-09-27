# Release 0.32.4

## Business-view entry point

- Preserve the complete recognized document-detail selection when a repeated
  product-catalog key prevents a flat join. The existing document model still
  validates headers, line grain, cancellations and missing references.
- The ambiguous catalog relation remains unsafe and is never recommended or
  materialized. The response explicitly identifies the guarded document fallback.
- Currency mismatches, zero overlap, unrecognized detail models and partial
  detail selections do not qualify for this fallback.
- A failed multi-period selection no longer silently becomes its first sheet.
- This does not certify source amounts or automatically remove duplicates.

## Exploration

- Show relationship detection as loading, not a premature empty result.
- Keep catalog-cost recommendations separate from realized-expense advice.

## Verification

- Synthetic header/detail regression: both periods remain included, an orphan
  and a cancelled sale remain excluded, and an ambiguous catalog cannot multiply
  revenue. Mixed-currency and partial-selection guards are covered.
- Browser checks exercise the real upload, cleaning, business-view and summary
  paths with unique and repeated catalog keys at desktop/mobile widths.
- The local workbook audit supports `--relationship-flow` for the production
  entry point. Private workbook inputs and outputs are not committed.

No database migration, plan change, payment activation or paid infrastructure.
