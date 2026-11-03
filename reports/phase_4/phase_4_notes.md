# Phase 4 — Non-AI Streamlit Dashboard

## Status

Implementation: completed.
Automated data tests: 8 passed.
Manual interface checks: passed.

## Data Source

Verified local SQLite database:
`database/ecommerce.db`.

Database connections are read-only and explicitly closed.

## Dashboard Sections

- Overview.
- Sales.
- Customers.
- Operations.

Gemini integration is not enabled in this phase.

## Filters

- Order-date range.
- Order status.
- Delivery state.
- Payment method.

Empty multiselect filters mean all values.

The default order status is Delivered.

All tabs follow the selected order cohort.
Operations dates refer to order dates, not shipment or return dates.

## Main Data Grain

One row per selected order.

Order items and return records are aggregated before joining.
The loader rejects duplicate order IDs.

Category sales use a separate item-level aggregation under the same
order filters.

## Metric Definitions

- Selected order value: sum of final_amount, including tax and shipping.
- Merchandise revenue: selected orders' item revenue.
- Item profit: selected orders' item revenue minus item cost.
- Average order value: selected order value divided by selected orders.
- Repeat customer: customer with at least two selected orders.
- Return-record counts include every return status.

Selected order value is not automatically realized revenue.
Item profit is not net business profit.

## Shipment Limitation

Original duration fields and diagnostic flags remain in the database.

The dashboard uses recorded-date delivery duration.

Possible year-end-clipping records are excluded from duration and
delay metrics by default, with an explicit checkbox to include them.

The metric denominator is displayed.
The diagnostic flag is not proof of the generator's implementation.

## Caching

Query results are cached with a five-minute TTL.
The database modification signature is included in cache keys.
A manual cache refresh button is available.

SQLite connection objects are not cached.

## Validation

Automated data tests cover:
- All-order count and uniqueness.
- Delivered-order count.
- Order-value reconciliation.
- Merchandise revenue and item-profit reconciliation.
- Category-total reconciliation.
- Combined filters.
- Empty results.
- Preservation of boundary flags.

Manual UI checks:
Record actual results after testing.

## Remaining Work

- Gemini integration.
- AI SQL validation and evaluation.
- Companion Power BI report.
- Final screenshots, demo, and README.