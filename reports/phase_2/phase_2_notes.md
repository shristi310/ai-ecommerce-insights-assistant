# Phase 2 — Data Preparation Notes

## Dataset

Indian E-Commerce Sales & Customer Analytics Dataset.

The dataset is synthetic and is used for learning and portfolio purposes.

## Completed Preparation

- Inspected all downloaded CSV files.
- Preserved the original files in `data/raw/`.
- Converted documented numeric, date, and Boolean fields.
- Preserved missing values allowed by the dictionary.
- Verified required fields and primary-key uniqueness.
- Verified documented foreign-key references.
- Exported nine business tables to `data/processed/`.
- Preserved all rows during preparation.
- Created a separate enriched shipment file in
  `data/analysis_ready/shipments_enriched.csv`.

## Important Definitions

- Customer summary fields use non-Failed orders.
- Customer recency uses `2025-12-31` as its reference date.
- Item revenue excludes separately listed order tax and shipping.
- Item profit is `item_revenue - item_cost`.
- Item profit is not net business profit.
- Campaign ROI follows the dataset's documented formula:
  `(revenue_generated - campaign_cost) / campaign_cost`.
- Negative item profit and campaign ROI may be valid.

## Missing Values

Allowed missing values were preserved rather than filled automatically.

No ages, delivery dates, ratings, campaign IDs, or coupon codes
were invented.

## Simulation Caveats

- `customer_segment` is a latent simulation segment.
- `return_rate_baseline` is a simulation parameter.
- Customer status and loyalty tier are precomputed derived attributes.
- Simulated campaign impressions and clicks are not observed
  ad-platform data.

## Validation Status

Business validation was executed:
- Total implemented checks: 82.
- Checks passed: 81.
- Checks requiring review: 1.
- The shipment-duration discrepancy was investigated and documented.

Outstanding findings:
One accepted source-data limitation remains: 910 shipments have
stored delivery durations that differ from their recorded date
differences. Details and handling are documented below.

No business-rule discrepancies were automatically corrected.
The original validation results remain unchanged.

## Shipment Duration Discrepancy

Business validation found 910 shipments whose stored `delivery_days`
did not equal `actual_delivery_date - dispatch_date`.

The first 20 diagnostic examples all had an actual delivery date
of `2025-12-31` and stored durations longer than their recorded
date differences.

### Possible Cause

Synthetic delivery dates may have been capped at the dataset's
year-end boundary.

This explanation remains a hypothesis. The generator's
implementation has not been verified.

### Full-Dataset Diagnostic Results

- Total shipments: 89,681.
- Comparable shipment durations: 87,360.
- Stored duration mismatches: 910.
- Mismatches matching the possible year-end-clipping pattern: 910.
- Other duration mismatches: 0.
- Duration null mismatches: 0.
- Original raw and processed files remain unchanged.

### Handling

- Preserved original shipment records and `delivery_days`.
- Created `data/analysis_ready/shipments_enriched.csv`.
- Added `delivery_days_calculated` from recorded dates.
- Added `delivery_days_mismatch`.
- Added `possible_year_end_clipping` as a diagnostic flag,
  not a confirmed explanation.
- Did not alter the original `delayed_flag`.
- Will label calculated duration as recorded-date delivery duration.
- Will disclose the boundary limitation in shipment-duration
  and delay analysis.

### Disposition

Accepted as a documented source-data limitation for this
portfolio project.

The discrepancy was investigated and documented, not silently
corrected or changed to a passed check.

## Phase 2 Completion Status

Complete with one documented source-data limitation.

The prepared tables are ready for Phase 3: SQLite database creation.