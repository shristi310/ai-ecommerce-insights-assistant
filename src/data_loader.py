from contextlib import closing
import sqlite3

import pandas as pd

from src.config import DATABASE_PATH


def database_signature():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            "Database not found. Run database/create_database.py first."
        )

    stat = DATABASE_PATH.stat()
    return (stat.st_mtime_ns, stat.st_size)


def read_query(sql, params=()):
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(f"Missing database: {DATABASE_PATH}")

    uri = DATABASE_PATH.resolve().as_uri() + "?mode=ro"

    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA foreign_keys = ON")

        return pd.read_sql_query(
            sql,
            connection,
            params=params,
        )


def get_filter_options():
    bounds = read_query(
        """
        SELECT MIN(order_date) AS first_date,
               MAX(order_date) AS last_date
        FROM orders
        """
    ).iloc[0]

    if pd.isna(bounds["first_date"]):
        raise ValueError("The orders table is empty.")

    return {
        "first_date": pd.Timestamp(bounds["first_date"]).date(),
        "last_date": pd.Timestamp(bounds["last_date"]).date(),
        "statuses": read_query(
            "SELECT DISTINCT order_status FROM orders "
            "ORDER BY order_status"
        )["order_status"].tolist(),
        "states": read_query(
            "SELECT DISTINCT delivery_state FROM orders "
            "ORDER BY delivery_state"
        )["delivery_state"].tolist(),
        "payment_methods": read_query(
            "SELECT DISTINCT payment_method FROM payments "
            "ORDER BY payment_method"
        )["payment_method"].tolist(),
    }


def build_where(start, end, statuses, states, payment_methods):
    clauses = ["o.order_date BETWEEN ? AND ?"]
    params = [str(start), str(end)]

    selections = [
        ("o.order_status", statuses),
        ("o.delivery_state", states),
        ("p.payment_method", payment_methods),
    ]

    for column, values in selections:
        if values:
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{column} IN ({placeholders})")
            params.extend(values)

    return " AND ".join(clauses), params


def load_order_cohort(
    start,
    end,
    statuses=(),
    states=(),
    payment_methods=(),
):
    where, params = build_where(
        start, end, statuses, states, payment_methods
    )

    sql = f"""
        WITH item_totals AS (
            SELECT
                order_id,
                SUM(quantity) AS units,
                SUM(item_revenue) AS merchandise_revenue,
                SUM(profit) AS item_profit
            FROM order_items
            GROUP BY order_id
        ),
        return_totals AS (
            SELECT
                order_id,
                COUNT(*) AS return_records
            FROM returns
            GROUP BY order_id
        )
        SELECT
            o.order_id,
            o.customer_id,
            o.order_date,
            o.order_status,
            o.delivery_state,
            o.final_amount,
            c.customer_segment,
            p.payment_method,
            p.payment_status,
            i.units,
            i.merchandise_revenue,
            i.item_profit,
            s.shipment_id,
            s.delivery_status,
            s.actual_delivery_date,
            s.delivery_days_calculated,
            s.delayed_flag,
            s.possible_year_end_clipping,
            COALESCE(r.return_records, 0) AS return_records
        FROM orders AS o
        JOIN customers AS c
            ON c.customer_id = o.customer_id
        JOIN payments AS p
            ON p.order_id = o.order_id
        JOIN item_totals AS i
            ON i.order_id = o.order_id
        LEFT JOIN shipments AS s
            ON s.order_id = o.order_id
        LEFT JOIN return_totals AS r
            ON r.order_id = o.order_id
        WHERE {where}
        ORDER BY o.order_date, o.order_id
    """

    frame = read_query(sql, params)

    if frame["order_id"].duplicated().any():
        raise ValueError("Unexpected duplicate orders in dashboard data.")

    for column in ["order_date", "actual_delivery_date"]:
        frame[column] = pd.to_datetime(frame[column], errors="raise")

    return frame


def load_category_sales(
    start,
    end,
    statuses=(),
    states=(),
    payment_methods=(),
):
    where, params = build_where(
        start, end, statuses, states, payment_methods
    )

    sql = f"""
        SELECT
            pr.category,
            SUM(oi.quantity) AS units,
            COUNT(DISTINCT o.order_id) AS orders_containing_category,
            SUM(oi.item_revenue) AS merchandise_revenue,
            SUM(oi.profit) AS item_profit
        FROM order_items AS oi
        JOIN orders AS o
            ON o.order_id = oi.order_id
        JOIN products AS pr
            ON pr.product_id = oi.product_id
        JOIN payments AS p
            ON p.order_id = o.order_id
        WHERE {where}
        GROUP BY pr.category
        ORDER BY merchandise_revenue DESC
    """

    return read_query(sql, params)