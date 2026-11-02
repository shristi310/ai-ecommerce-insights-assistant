from pathlib import Path
import sqlite3

import pandas as pd

from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "database" / "ecommerce.db"


def main():
    if not DATABASE.exists():
        raise FileNotFoundError("Build ecommerce.db first.")

    uri = DATABASE.resolve().as_uri() + "?mode=ro"

    query = """
        SELECT
            order_status,
            COUNT(*) AS order_count,
            ROUND(SUM(final_amount), 2) AS total_order_value
        FROM orders
        GROUP BY order_status
        ORDER BY order_count DESC
    """

    with closing(sqlite3.connect(uri, uri=True)) as connection:
        result = pd.read_sql_query(query, connection)

    print(result.to_string(index=False))

    if int(result["order_count"].sum()) != 100000:
        raise ValueError("Order count does not match the Phase 2 dataset.")

    print("\nSQL smoke test passed.")


if __name__ == "__main__":
    main()