from pathlib import Path
import json

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "processed"
REPORTS = ROOT / "reports" / "phase_2"
EXAMPLES = REPORTS / "validation_examples"

REFERENCE_DATE = pd.Timestamp("2025-12-31")

TABLES = [
    "customers",
    "products",
    "orders",
    "order_items",
    "payments",
    "shipments",
    "returns",
    "customer_reviews",
    "marketing_campaigns",
]

DATE_COLUMNS = {
    "customers": ["customer_signup_date", "last_order_date"],
    "products": ["product_launch_date"],
    "orders": ["order_date"],
    "payments": ["payment_date"],
    "shipments": [
        "dispatch_date",
        "expected_delivery_date",
        "actual_delivery_date",
    ],
    "returns": ["return_date"],
    "customer_reviews": ["review_date"],
    "marketing_campaigns": [
        "campaign_start_date",
        "campaign_end_date",
    ],
}

RESULTS = []


def load_tables():
    tables = {}

    for name in TABLES:
        path = DATA / f"{name}.csv"

        if not path.exists():
            raise FileNotFoundError(f"Missing processed file: {path}")

        # Preserve text identifiers and literal category values.
        df = pd.read_csv(
            path,
            keep_default_na=False,
            na_values=[""],
            low_memory=False,
        )

        for column in DATE_COLUMNS.get(name, []):
            df[column] = pd.to_datetime(
                df[column],
                format="%Y-%m-%d",
                errors="raise",
            )

        tables[name] = df

    return tables


def check(name, frame, bad_mask, severity="ERROR", note=""):
    bad = pd.Series(bad_mask, index=frame.index).fillna(True).astype(bool)
    failed = int(bad.sum())

    RESULTS.append(
        {
            "check": name,
            "severity": severity,
            "rows_checked": len(frame),
            "failed_rows": failed,
            "result": "PASS" if failed == 0 else "REVIEW",
            "note": note,
        }
    )

    if failed:
        frame.loc[bad].head(20).to_csv(
            EXAMPLES / f"{name}.csv",
            index=False,
            date_format="%Y-%m-%d",
        )


def compare_numbers(
    name,
    frame,
    actual_column,
    expected,
    tolerance=0.02,
    severity="ERROR",
    note="",
):
    expected = pd.Series(expected, index=frame.index)
    actual = pd.to_numeric(frame[actual_column], errors="coerce")
    expected = pd.to_numeric(expected, errors="coerce")

    evidence = frame.copy()
    evidence["expected_value"] = expected
    evidence["difference"] = actual - expected

    matches = np.isclose(
        actual.to_numpy(dtype=float),
        expected.to_numpy(dtype=float),
        atol=tolerance,
        rtol=0,
        equal_nan=False,
    )

    check(name, evidence, ~matches, severity, note)


def allowed(name, frame, column, values, nullable=False):
    valid = frame[column].isin(values)

    if nullable:
        valid = valid | frame[column].isna()

    check(name, frame, ~valid)


def numeric_range(
    name,
    frame,
    column,
    minimum=None,
    maximum=None,
    nullable=False,
):
    values = pd.to_numeric(frame[column], errors="coerce")
    valid = values.notna()

    if minimum is not None:
        valid = valid & values.ge(minimum)

    if maximum is not None:
        valid = valid & values.le(maximum)

    if nullable:
        valid = valid | frame[column].isna()

    check(name, frame, ~valid)


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    EXAMPLES.mkdir(parents=True, exist_ok=True)

    # Remove only old example files created by this validator.
    for path in EXAMPLES.glob("*.csv"):
        path.unlink()

    tables = load_tables()

    customers = tables["customers"]
    products = tables["products"]
    orders = tables["orders"]
    items = tables["order_items"]
    payments = tables["payments"]
    shipments = tables["shipments"]
    returns = tables["returns"]
    reviews = tables["customer_reviews"]
    campaigns = tables["marketing_campaigns"]

    # 1. Allowed categorical values.
    category_rules = [
        (
            "customers",
            "gender",
            ["Male", "Female", "Other"],
            False,
        ),
        (
            "customers",
            "customer_segment",
            ["Premium", "Regular", "Budget", "New"],
            False,
        ),
        (
            "customers",
            "preferred_device",
            ["Mobile App", "Mobile Web", "Desktop"],
            True,
        ),
        (
            "customers",
            "customer_status",
            ["Active", "At Risk", "Churned", "Never Purchased"],
            False,
        ),
        (
            "customers",
            "loyalty_tier",
            ["Bronze", "Silver", "Gold", "Platinum"],
            False,
        ),
        (
            "products",
            "product_type",
            ["Standard", "Premium", "Budget", "Exclusive"],
            False,
        ),
        (
            "orders",
            "order_status",
            ["Delivered", "Cancelled", "Returned", "Failed", "Processing"],
            False,
        ),
        (
            "payments",
            "payment_status",
            ["Success", "Pending", "Failed", "Refunded", "Not Charged"],
            False,
        ),
        (
            "shipments",
            "delivery_status",
            ["Delivered", "Delivered then Returned", "Cancelled in Transit"],
            False,
        ),
        (
            "returns",
            "return_status",
            ["Approved", "Rejected", "Pending", "Refund Completed"],
            False,
        ),
        (
            "customer_reviews",
            "review_sentiment",
            ["Positive", "Neutral", "Negative"],
            True,
        ),
        (
            "marketing_campaigns",
            "target_segment",
            ["Premium", "Regular", "Budget", "New", "All"],
            False,
        ),
    ]

    for table, column, values, nullable in category_rules:
        allowed(
            f"{table}_{column}_allowed",
            tables[table],
            column,
            values,
            nullable,
        )

    # 2. Numeric ranges.
    numeric_range("customer_age", customers, "age", 18, 70, True)
    numeric_range("pincode_prefix", customers, "pincode_prefix", 100, 899)
    numeric_range("item_quantity", items, "quantity", 1, 8)
    numeric_range("item_discount", items, "discount_percentage", 0, 60)
    numeric_range("order_discount", orders, "discount_percentage", 0, 30)
    numeric_range(
        "campaign_discount",
        campaigns,
        "discount_percentage",
        5,
        30,
    )
    numeric_range(
        "product_rating",
        products,
        "rating_average",
        1,
        5,
        True,
    )
    numeric_range("review_rating", reviews, "rating", 1, 5)
    numeric_range(
        "return_baseline",
        products,
        "return_rate_baseline",
        0.005,
        0.5,
    )
    numeric_range(
        "shipment_delivery_days",
        shipments,
        "delivery_days",
        0,
        nullable=True,
    )

    allowed(
        "shipment_delay_flag_values",
        shipments,
        "delayed_flag",
        [0, 1],
    )

    nonnegative_columns = {
        "customers": ["total_orders", "total_spend", "average_order_value"],
        "products": ["rating_count", "stock_quantity"],
        "orders": ["subtotal", "shipping_fee", "tax_amount", "final_amount"],
        "order_items": ["item_revenue", "item_cost"],
        "payments": ["amount_paid", "transaction_fee", "refund_amount"],
        "returns": ["refund_amount"],
        "marketing_campaigns": [
            "impressions",
            "clicks",
            "conversions",
            "campaign_cost",
            "revenue_generated",
        ],
    }

    for table, columns in nonnegative_columns.items():
        for column in columns:
            numeric_range(
                f"{table}_{column}_nonnegative",
                tables[table],
                column,
                minimum=0,
            )

    check("product_price_positive", products, products["price"].le(0))
    check("product_cost_positive", products, products["cost_price"].le(0))
    check(
        "product_cost_below_price",
        products,
        products["cost_price"].ge(products["price"]),
    )
    check("item_price_positive", items, items["unit_price"].le(0))

    # 3. Item formulas.
    compare_numbers(
        "item_revenue_formula",
        items,
        "item_revenue",
        (
            items["quantity"]
            * items["unit_price"]
            * (1 - items["discount_percentage"] / 100)
        ).round(2),
    )

    compare_numbers(
        "item_profit_formula",
        items,
        "profit",
        items["item_revenue"] - items["item_cost"],
    )

    item_cost_check = items.merge(
        products[["product_id", "cost_price"]],
        on="product_id",
        how="left",
        validate="many_to_one",
    )

    compare_numbers(
        "item_cost_formula",
        item_cost_check,
        "item_cost",
        item_cost_check["quantity"] * item_cost_check["cost_price"],
        severity="WARNING",
        note="Review possible rounding or catalog cost assumptions.",
    )

    # 4. Order formulas.
    line_totals = items.groupby("order_id", as_index=False).agg(
        expected_subtotal=("item_revenue", "sum"),
        line_count=("order_item_id", "size"),
    )

    order_check = orders.merge(
        line_totals,
        on="order_id",
        how="left",
        validate="one_to_one",
    )

    check(
        "orders_have_items",
        order_check,
        order_check["line_count"].isna(),
    )

    compare_numbers(
        "order_subtotal_formula",
        order_check,
        "subtotal",
        order_check["expected_subtotal"],
    )

    compare_numbers(
        "order_final_amount_formula",
        orders,
        "final_amount",
        orders["subtotal"] + orders["shipping_fee"] + orders["tax_amount"],
    )

    compare_numbers(
        "order_tax_approximately_five_percent",
        orders,
        "tax_amount",
        (orders["subtotal"] * 0.05).round(2),
        severity="WARNING",
        note="Dictionary describes GST as approximate.",
    )

    check(
        "shipping_waiver_above_499",
        orders,
        orders["subtotal"].gt(499) & orders["shipping_fee"].gt(0.02),
        severity="WARNING",
        note="Check the dictionary's shipping-waiver description.",
    )

    # 5. Customer summaries: non-Failed orders, exactly as documented.
    eligible_orders = orders.loc[
        orders["order_status"].ne("Failed")
    ].copy()

    customer_totals = eligible_orders.groupby(
        "customer_id",
        as_index=False,
    ).agg(
        expected_total_orders=("order_id", "size"),
        expected_total_spend=("final_amount", "sum"),
        expected_last_order_date=("order_date", "max"),
    )

    customer_check = customers.merge(
        customer_totals,
        on="customer_id",
        how="left",
        validate="one_to_one",
    )

    customer_check["expected_total_orders"] = (
        customer_check["expected_total_orders"].fillna(0)
    )
    customer_check["expected_total_spend"] = (
        customer_check["expected_total_spend"].fillna(0)
    )

    compare_numbers(
        "customer_total_orders",
        customer_check,
        "total_orders",
        customer_check["expected_total_orders"],
        tolerance=0,
    )

    compare_numbers(
        "customer_total_spend",
        customer_check,
        "total_spend",
        customer_check["expected_total_spend"],
    )

    expected_aov = (
        customer_check["expected_total_spend"]
        .div(
            customer_check["expected_total_orders"].replace(0, np.nan)
        )
        .fillna(0)
    )

    compare_numbers(
        "customer_average_order_value",
        customer_check,
        "average_order_value",
        expected_aov,
    )

    dates_match = (
        customer_check["last_order_date"].eq(
            customer_check["expected_last_order_date"]
        )
        | (
            customer_check["last_order_date"].isna()
            & customer_check["expected_last_order_date"].isna()
        )
    )

    check(
        "customer_last_order_date",
        customer_check,
        ~dates_match,
    )

    recency_days = (
        REFERENCE_DATE - customer_check["expected_last_order_date"]
    ).dt.days

    expected_status = pd.Series(
        "Churned",
        index=customer_check.index,
    )
    expected_status.loc[recency_days.le(180)] = "At Risk"
    expected_status.loc[recency_days.le(90)] = "Active"
    expected_status.loc[
        customer_check["expected_total_orders"].eq(0)
    ] = "Never Purchased"

    customer_check["expected_customer_status"] = expected_status

    check(
        "customer_status_formula",
        customer_check,
        customer_check["customer_status"].ne(expected_status),
    )

    # 6. Shipment formulas and chronology.
    compare_numbers(
        "shipment_delivery_days_formula",
        shipments.loc[shipments["actual_delivery_date"].notna()].copy(),
        "delivery_days",
        (
            shipments.loc[
                shipments["actual_delivery_date"].notna(),
                "actual_delivery_date",
            ]
            - shipments.loc[
                shipments["actual_delivery_date"].notna(),
                "dispatch_date",
            ]
        ).dt.days,
        tolerance=0,
    )

    check(
        "shipment_delivery_nulls_match",
        shipments,
        (
            shipments["actual_delivery_date"].isna()
            != shipments["delivery_days"].isna()
        ),
    )

    check(
        "shipment_expected_before_dispatch",
        shipments,
        shipments["expected_delivery_date"].lt(
            shipments["dispatch_date"]
        ),
    )

    check(
        "shipment_actual_before_dispatch",
        shipments,
        (
            shipments["actual_delivery_date"].notna()
            & shipments["actual_delivery_date"].lt(
                shipments["dispatch_date"]
            )
        ),
    )

    delivered_shipments = shipments.loc[
        shipments["actual_delivery_date"].notna()
    ].copy()

    expected_delay = delivered_shipments[
        "actual_delivery_date"
    ].gt(delivered_shipments["expected_delivery_date"]).astype(int)

    compare_numbers(
        "shipment_delay_flag_formula",
        delivered_shipments,
        "delayed_flag",
        expected_delay,
        tolerance=0,
    )

    check(
        "shipment_missing_actual_date_status",
        shipments,
        (
            shipments["actual_delivery_date"].isna()
            & shipments["delivery_status"].ne("Cancelled in Transit")
        ),
    )

    shipment_order_check = shipments.merge(
        orders[["order_id", "order_date"]],
        on="order_id",
        how="left",
        validate="many_to_one",
    )

    check(
        "shipment_dispatch_before_order",
        shipment_order_check,
        shipment_order_check["dispatch_date"].lt(
            shipment_order_check["order_date"]
        ),
    )

    # 7. Payment coverage and chronology.
    check(
        "payment_order_unique",
        payments,
        payments["order_id"].duplicated(keep=False),
    )

    check(
        "all_orders_have_payment_record",
        orders,
        ~orders["order_id"].isin(payments["order_id"]),
    )

    payment_order_check = payments.merge(
        orders[["order_id", "order_date"]],
        on="order_id",
        how="left",
        validate="many_to_one",
    )

    check(
        "payment_before_order",
        payment_order_check,
        payment_order_check["payment_date"].lt(
            payment_order_check["order_date"]
        ),
        severity="WARNING",
    )

    # 8. Review/return customer and purchased-product consistency.
    purchased_pairs = items[
        ["order_id", "product_id"]
    ].drop_duplicates()

    for table_name, date_column in [
        ("returns", "return_date"),
        ("customer_reviews", "review_date"),
    ]:
        frame = tables[table_name]

        linked = frame.merge(
            orders[
                ["order_id", "customer_id", "order_date"]
            ].rename(
                columns={"customer_id": "expected_customer_id"}
            ),
            on="order_id",
            how="left",
            validate="many_to_one",
        )

        check(
            f"{table_name}_customer_matches_order",
            linked,
            linked["customer_id"].ne(linked["expected_customer_id"]),
        )

        check(
            f"{table_name}_date_before_order",
            linked,
            linked[date_column].lt(linked["order_date"]),
        )

        product_check = frame.merge(
            purchased_pairs.assign(purchased_pair_exists=True),
            on=["order_id", "product_id"],
            how="left",
            validate="many_to_one",
        )

        check(
            f"{table_name}_product_belongs_to_order",
            product_check,
            product_check["purchased_pair_exists"].isna(),
        )

    # 9. Campaign definitions.
    check(
        "campaign_end_before_start",
        campaigns,
        campaigns["campaign_end_date"].lt(
            campaigns["campaign_start_date"]
        ),
    )

    attributed_orders = orders.loc[
        orders["campaign_id"].notna()
    ].copy()

    campaign_totals = attributed_orders.groupby(
        "campaign_id",
        as_index=False,
    ).agg(
        expected_conversions=("order_id", "size"),
        expected_revenue=("final_amount", "sum"),
    )

    campaign_check = campaigns.merge(
        campaign_totals,
        on="campaign_id",
        how="left",
        validate="one_to_one",
    )

    campaign_check["expected_conversions"] = (
        campaign_check["expected_conversions"].fillna(0)
    )
    campaign_check["expected_revenue"] = (
        campaign_check["expected_revenue"].fillna(0)
    )

    compare_numbers(
        "campaign_conversion_total",
        campaign_check,
        "conversions",
        campaign_check["expected_conversions"],
        tolerance=0,
    )

    compare_numbers(
        "campaign_revenue_total",
        campaign_check,
        "revenue_generated",
        campaign_check["expected_revenue"],
        note="Uses all attributed orders as stated in the dictionary.",
    )

    positive_cost = campaigns.loc[
        campaigns["campaign_cost"].gt(0)
    ].copy()

    compare_numbers(
        "campaign_roi_formula",
        positive_cost,
        "roi",
        (
            positive_cost["revenue_generated"]
            - positive_cost["campaign_cost"]
        ) / positive_cost["campaign_cost"],
        tolerance=0.02,
    )

    campaign_links = attributed_orders.merge(
        campaigns[
            [
                "campaign_id",
                "channel",
                "campaign_start_date",
                "campaign_end_date",
            ]
        ],
        on="campaign_id",
        how="left",
        validate="many_to_one",
    )

    check(
        "campaign_channel_matches_order",
        campaign_links,
        campaign_links["marketing_channel"].ne(
            campaign_links["channel"]
        ),
    )

    check(
        "campaign_order_inside_window",
        campaign_links,
        (
            campaign_links["order_date"].lt(
                campaign_links["campaign_start_date"]
            )
            | campaign_links["order_date"].gt(
                campaign_links["campaign_end_date"]
            )
        ),
    )

    # 10. Save reports.
    result_df = pd.DataFrame(RESULTS)
    result_df.to_csv(
        REPORTS / "business_validation_results.csv",
        index=False,
    )

    failed = result_df.loc[result_df["failed_rows"].gt(0)]
    error_checks = failed.loc[failed["severity"].eq("ERROR")]
    warning_checks = failed.loc[failed["severity"].eq("WARNING")]

    overview = {
        "checks_run": len(result_df),
        "checks_passed": int(result_df["failed_rows"].eq(0).sum()),
        "error_checks_to_review": len(error_checks),
        "warning_checks_to_review": len(warning_checks),
        "reference_date": str(REFERENCE_DATE.date()),
        "data_modified": False,
        "status": (
            "PASS_FOR_IMPLEMENTED_CHECKS"
            if failed.empty
            else "REVIEW_REQUIRED"
        ),
    }

    with (REPORTS / "business_validation_overview.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(overview, file, indent=2)

    text = [
        "PHASE 2 — BUSINESS VALIDATION",
        "",
        json.dumps(overview, indent=2),
        "",
        result_df.to_string(index=False),
        "",
        "IMPORTANT:",
        "- Raw and processed data were not modified.",
        "- Findings require review; they are not automatic corrections.",
        "- Passing these checks does not prove every possible rule.",
        "- Example files may contain customer-level information.",
    ]

    (REPORTS / "business_validation_report.txt").write_text(
        "\n".join(text),
        encoding="utf-8",
    )

    print("\n" + json.dumps(overview, indent=2))

    if failed.empty:
        print("\nAll implemented checks passed.")
    else:
        print("\nCHECKS TO REVIEW")
        print(
            failed[
                ["check", "severity", "failed_rows"]
            ].to_string(index=False)
        )

    print("\nReports saved in reports/phase_2/.")
    print("No source or processed CSVs were modified.")


if __name__ == "__main__":
    main()