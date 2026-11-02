-- Indian E-Commerce Business Analysis
--
-- These queries intentionally distinguish:
-- 1. All placed orders.
-- 2. Non-Failed order value, matching customer-summary definitions.
-- 3. Delivered-order merchandise revenue and item profit.
--
-- These are different metrics and should not all be named "revenue".


-- 1. Number of orders by final status.
SELECT
    order_status,
    COUNT(*) AS order_count
FROM orders
GROUP BY order_status
ORDER BY order_count DESC;


-- 2. Non-Failed order value, including tax and shipping.
SELECT
    COUNT(*) AS non_failed_orders,
    ROUND(SUM(final_amount), 2) AS non_failed_order_value,
    ROUND(AVG(final_amount), 2) AS average_non_failed_order_value
FROM orders
WHERE order_status <> 'Failed';


-- 3. Monthly Delivered-order merchandise revenue and item profit.
SELECT
    SUBSTR(o.order_date, 1, 7) AS order_month,
    ROUND(SUM(oi.item_revenue), 2) AS merchandise_revenue,
    ROUND(SUM(oi.item_cost), 2) AS item_cost,
    ROUND(SUM(oi.profit), 2) AS item_profit
FROM order_items AS oi
JOIN orders AS o
    ON o.order_id = oi.order_id
WHERE o.order_status = 'Delivered'
GROUP BY SUBSTR(o.order_date, 1, 7)
ORDER BY order_month;


-- 4. Delivered-order category performance.
SELECT
    p.category,
    SUM(oi.quantity) AS units,
    ROUND(SUM(oi.item_revenue), 2) AS merchandise_revenue,
    ROUND(SUM(oi.profit), 2) AS item_profit,
    ROUND(
        100.0 * SUM(oi.profit)
        / NULLIF(SUM(oi.item_revenue), 0),
        2
    ) AS item_profit_margin_pct
FROM order_items AS oi
JOIN orders AS o
    ON o.order_id = oi.order_id
JOIN products AS p
    ON p.product_id = oi.product_id
WHERE o.order_status = 'Delivered'
GROUP BY p.category
ORDER BY merchandise_revenue DESC;


-- 5. Top customers by documented non-Failed order value.
SELECT
    customer_id,
    city,
    state,
    total_orders,
    ROUND(total_spend, 2) AS non_failed_order_value,
    customer_status
FROM customers
WHERE total_orders > 0
ORDER BY total_spend DESC
LIMIT 10;


-- 6. Repeat-customer rate among non-Failed-order purchasers.
SELECT
    COUNT(*) AS purchasing_customers,
    SUM(CASE WHEN total_orders >= 2 THEN 1 ELSE 0 END)
        AS repeat_customers,
    ROUND(
        100.0
        * SUM(CASE WHEN total_orders >= 2 THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0),
        2
    ) AS repeat_customer_rate_pct
FROM customers
WHERE total_orders > 0;


-- 7. Payment outcomes: do not assume every order was paid.
SELECT
    payment_status,
    payment_method,
    COUNT(*) AS payment_records,
    ROUND(SUM(amount_paid), 2) AS recorded_amount_paid,
    ROUND(SUM(refund_amount), 2) AS recorded_refunds,
    ROUND(SUM(transaction_fee), 2) AS recorded_transaction_fees
FROM payments
GROUP BY payment_status, payment_method
ORDER BY payment_records DESC;


-- 8. Recorded-date shipment duration, with boundary flag visible.
SELECT
    possible_year_end_clipping,
    COUNT(*) AS shipments_with_recorded_delivery,
    ROUND(AVG(delivery_days_calculated), 2)
        AS average_recorded_date_duration,
    ROUND(AVG(delivery_days), 2)
        AS average_original_stored_duration
FROM shipments
WHERE actual_delivery_date IS NOT NULL
GROUP BY possible_year_end_clipping;


-- 9. Shipment delivery outcomes.
SELECT
    delivery_status,
    COUNT(*) AS shipment_count
FROM shipments
GROUP BY delivery_status
ORDER BY shipment_count DESC;


-- 10. Return records by status and reason.
-- These are record counts, not a return-rate calculation.
SELECT
    return_status,
    return_reason,
    COUNT(*) AS return_records,
    ROUND(SUM(refund_amount), 2) AS recorded_return_refund_amount
FROM returns
GROUP BY return_status, return_reason
ORDER BY return_records DESC;


-- 11. Product review summary.
SELECT
    p.category,
    COUNT(*) AS review_count,
    ROUND(AVG(r.rating), 2) AS average_review_rating
FROM customer_reviews AS r
JOIN products AS p
    ON p.product_id = r.product_id
GROUP BY p.category
ORDER BY average_review_rating DESC, review_count DESC;


-- 12. Campaign performance as defined by the synthetic dataset.
-- Attributed order value is not necessarily realized revenue.
SELECT
    campaign_id,
    campaign_name,
    channel,
    conversions AS attributed_orders,
    ROUND(revenue_generated, 2) AS attributed_order_value,
    ROUND(campaign_cost, 2) AS simulated_campaign_cost,
    ROUND(roi, 2) AS dataset_roi
FROM marketing_campaigns
ORDER BY attributed_order_value DESC
LIMIT 10;