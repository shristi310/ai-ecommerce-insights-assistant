from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_loader import (
    get_filter_options,
    load_category_sales,
    load_order_cohort,
    read_query,
)


class DashboardDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.options = get_filter_options()
        cls.start = cls.options["first_date"]
        cls.end = cls.options["last_date"]

        cls.all_orders = load_order_cohort(cls.start, cls.end)

        cls.delivered = load_order_cohort(
            cls.start,
            cls.end,
            statuses=("Delivered",),
        )

    def test_all_order_count_and_grain(self):
        self.assertEqual(len(self.all_orders), 100000)
        self.assertTrue(self.all_orders["order_id"].is_unique)

    def test_delivered_count(self):
        self.assertEqual(len(self.delivered), 80679)
        self.assertTrue(
            self.delivered["order_status"].eq("Delivered").all()
        )

    def test_order_value_matches_direct_sql(self):
        expected = read_query(
            """
            SELECT SUM(final_amount) AS value
            FROM orders
            WHERE order_status = 'Delivered'
            """
        ).iloc[0]["value"]

        self.assertTrue(
            np.isclose(
                self.delivered["final_amount"].sum(),
                expected,
                atol=0.02,
                rtol=0,
            )
        )

    def test_merchandise_and_profit_match_direct_sql(self):
        expected = read_query(
            """
            SELECT
                SUM(oi.item_revenue) AS revenue,
                SUM(oi.profit) AS profit
            FROM order_items AS oi
            JOIN orders AS o ON o.order_id = oi.order_id
            WHERE o.order_status = 'Delivered'
            """
        ).iloc[0]

        self.assertTrue(
            np.isclose(
                self.delivered["merchandise_revenue"].sum(),
                expected["revenue"],
                atol=0.02,
                rtol=0,
            )
        )

        self.assertTrue(
            np.isclose(
                self.delivered["item_profit"].sum(),
                expected["profit"],
                atol=0.02,
                rtol=0,
            )
        )

    def test_category_totals_reconcile(self):
        categories = load_category_sales(
            self.start,
            self.end,
            statuses=("Delivered",),
        )

        self.assertTrue(
            np.isclose(
                categories["merchandise_revenue"].sum(),
                self.delivered["merchandise_revenue"].sum(),
                atol=0.02,
                rtol=0,
            )
        )

    def test_combined_filters(self):
        state = self.options["states"][0]
        method = self.options["payment_methods"][0]

        selected = load_order_cohort(
            self.start,
            self.end,
            statuses=("Delivered",),
            states=(state,),
            payment_methods=(method,),
        )

        expected = self.delivered.loc[
            self.delivered["delivery_state"].eq(state)
            & self.delivered["payment_method"].eq(method)
        ]

        self.assertEqual(
            set(selected["order_id"]),
            set(expected["order_id"]),
        )

    def test_empty_result(self):
        selected = load_order_cohort(
            self.start,
            self.end,
            states=("__NONEXISTENT_STATE__",),
        )

        self.assertTrue(selected.empty)

    def test_boundary_flags_preserved(self):
        self.assertEqual(
            int(
                self.all_orders["possible_year_end_clipping"]
                .fillna(0)
                .sum()
            ),
            910,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)