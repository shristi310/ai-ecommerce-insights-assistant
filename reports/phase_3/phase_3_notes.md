# Phase 3 — SQLite Database

## Status

Database build: completed.
Independent verification: passed.
SQL smoke test: passed.

Database implementation and verification are complete.
Git commit and push status are tracked separately.

## Inputs

- Eight business CSV files from `data/processed/`.
- Enriched shipments from
  `data/analysis_ready/shipments_enriched.csv`.
- Schema definitions from `data/raw/data_dictionary.csv`.

The original `data/processed/shipments.csv` is preserved but is
not loaded as a second shipment table.

## Database Design

- Nine business tables.
- Explicit SQLite column types.
- STRICT tables.
- Primary keys and required fields.
- Documented foreign-key relationships.
- Foreign-key enforcement enabled during database creation.
- Unique `order_id` constraints for payments and shipments,
  matching the observed dataset structure.
- 19 explicit indexes on foreign keys and selected analytical filters.

Dates are stored as ISO `YYYY-MM-DD` text.
Boolean fields are stored as integer `0` or `1`.
Optional missing values are stored as `NULL`.
Monetary fields use `REAL` with analytical rounding tolerances.

The database is built in a temporary file, verified, and then
moved into place as `database/ecommerce.db`.

Raw and processed CSV files are not modified by the build.

## Database Tables

| Table | Rows |
|---|---:|
| customers | 25,000 |
| products | 550 |
| marketing_campaigns | 151 |
| orders | 100,000 |
| order_items | 254,331 |
| payments | 100,000 |
| shipments | 89,681 |
| returns | 12,075 |
| customer_reviews | 77,530 |

## Verification

The database build and independent verification passed.

Confirmed results:
- Database integrity check: `ok`.
- Foreign-key violations: `0`.
- Business tables: `9`.
- Source and database row counts matched.
- Column types, nullability, and primary-key declarations matched.
- Source and database missing-value counts matched.
- Shipment diagnostic totals were preserved.

Verification is not a full cell-by-cell comparison and does not
prove that every possible business rule is satisfied.

## SQL Smoke Test

The smoke test successfully queried order counts and order values
by status and confirmed a total of 100,000 orders.

| Order status | Orders |
|---|---:|
| Delivered | 80,679 |
| Cancelled | 8,073 |
| Returned | 6,681 |
| Failed | 2,880 |
| Processing | 1,687 |
| Total | 100,000 |

The smoke test's `total_order_value` is the sum of `final_amount`
within each status. It is not necessarily collected payments
or realized revenue.

## Shipment Limitation

The 910 duration discrepancies identified in Phase 2 are preserved.

The `shipments` table includes:
- Original `delivery_days`.
- `delivery_days_calculated`.
- `delivery_days_mismatch`.
- `possible_year_end_clipping`.

Database verification confirmed:
- Shipment-duration mismatch flags: 910.
- Possible year-end-clipping flags: 910.

The clipping flag identifies a diagnostic pattern, not proof of
the generator's implementation.

Calculated durations represent differences between recorded dates.
They do not reconstruct an unobserved true delivery duration.

The boundary limitation must remain visible in shipment-duration
and delay analysis.

## Analytical Definitions

- Non-Failed order value matches the customer-summary definition.
- Non-Failed order value is not automatically realized revenue.
- Delivered-order merchandise revenue is a separate scoped metric.
- Item profit does not represent net business profit.
- Campaign ROI follows the synthetic dataset's definition.
- Return rates require a separately documented denominator.

## Reproducibility

Run these commands from the project root:

```powershell
python database/create_database.py
python database/create_database.py --verify
python database/run_smoke_test.py
```

Close database viewers before rebuilding.

The database file and generated verification report remain local.
The build script, generated schema, SQL analysis queries, smoke-test
script, and these notes are intended for version control.

## Next Phase

Phase 4: Build the non-AI Streamlit dashboard using the verified
SQLite database.

Gemini integration will be added after the dashboard is working
and its metrics have been checked.