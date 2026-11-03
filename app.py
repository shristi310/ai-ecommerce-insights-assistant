import pandas as pd
import plotly.express as px
import streamlit as st

from src.config import APP_TITLE, CACHE_TTL_SECONDS
from src.data_loader import (
    database_signature,
    get_filter_options,
    load_category_sales,
    load_order_cohort,
)


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📊",
    layout="wide",
)


@st.cache_data(ttl=CACHE_TTL_SECONDS, max_entries=2)
def cached_options(signature):
    return get_filter_options()


@st.cache_data(ttl=CACHE_TTL_SECONDS, max_entries=12)
def cached_orders(
    signature, start, end, statuses, states, payment_methods
):
    return load_order_cohort(
        start, end, statuses, states, payment_methods
    )


@st.cache_data(ttl=CACHE_TTL_SECONDS, max_entries=12)
def cached_categories(
    signature, start, end, statuses, states, payment_methods
):
    return load_category_sales(
        start, end, statuses, states, payment_methods
    )


def money(value):
    return f"₹{value:,.2f}"


def show_table(frame):
    st.dataframe(frame, use_container_width=True, hide_index=True)


def main():
    st.title(APP_TITLE)
    st.caption(
        "Synthetic Indian e-commerce data • "
        "Verified SQLite database • Non-AI dashboard"
    )

    try:
        signature = database_signature()
        options = cached_options(signature)
    except Exception as error:
        st.error(f"Could not open dashboard data: {error}")
        st.stop()

    with st.sidebar:
        st.header("Order cohort filters")

        start = st.date_input(
            "Order date: from",
            value=options["first_date"],
            min_value=options["first_date"],
            max_value=options["last_date"],
        )

        end = st.date_input(
            "Order date: to",
            value=options["last_date"],
            min_value=options["first_date"],
            max_value=options["last_date"],
        )

        statuses = st.multiselect(
            "Order status",
            options=options["statuses"],
            default=["Delivered"],
        )

        states = st.multiselect(
            "Delivery state",
            options=options["states"],
        )

        payment_methods = st.multiselect(
            "Payment method",
            options=options["payment_methods"],
        )

        st.caption(
            "An empty selection means all values for that filter. "
            "All tabs use order dates, not shipment or return dates."
        )

        if st.button("Refresh cached data"):
            st.cache_data.clear()
            st.rerun()

    if start > end:
        st.warning("The start date must not be after the end date.")
        st.stop()

    arguments = (
        signature,
        start,
        end,
        tuple(sorted(statuses)),
        tuple(sorted(states)),
        tuple(sorted(payment_methods)),
    )

    try:
        orders = cached_orders(*arguments)
        categories = cached_categories(*arguments)
    except Exception as error:
        st.error(f"Could not load filtered data: {error}")
        st.stop()

    if orders.empty:
        st.info("No orders match these filters. Adjust the sidebar.")
        st.stop()

    status_text = ", ".join(statuses) if statuses else "All statuses"

    st.caption(
        f"Order dates: {start} to {end} | "
        f"Status scope: {status_text} | "
        f"Selected orders: {len(orders):,}"
    )

    if not statuses or set(statuses) != {"Delivered"}:
        st.warning(
            "Your selection is not limited to Delivered orders. "
            "Values include the selected statuses and must not be "
            "interpreted automatically as realized revenue."
        )

    overview, sales, customers, operations = st.tabs(
        ["Overview", "Sales", "Customers", "Operations"]
    )

    with overview:
        order_value = orders["final_amount"].sum()
        merchandise = orders["merchandise_revenue"].sum()
        profit = orders["item_profit"].sum()

        a, b, c, d = st.columns(4)
        a.metric("Selected orders", f"{len(orders):,}")
        b.metric("Selected order value", money(order_value))
        c.metric("Merchandise revenue", money(merchandise))
        d.metric("Item profit", money(profit))

        st.caption(
            "Order value includes tax and shipping. Merchandise revenue "
            "does not. Item profit is not net business profit."
        )

        a, b = st.columns(2)
        a.metric(
            "Average selected order value",
            money(order_value / len(orders)),
        )
        b.metric(
            "Distinct selected customers",
            f"{orders['customer_id'].nunique():,}",
        )

        monthly = (
            orders.assign(
                month=orders["order_date"].dt.to_period("M").astype(str)
            )
            .groupby("month", as_index=False)
            .agg(
                selected_order_value=("final_amount", "sum"),
                merchandise_revenue=("merchandise_revenue", "sum"),
            )
        )

        fig = px.line(
            monthly,
            x="month",
            y=["selected_order_value", "merchandise_revenue"],
            markers=True,
            title="Monthly values for the selected order cohort",
            labels={
                "month": "Order month",
                "value": "INR",
                "variable": "Metric",
            },
        )
        st.plotly_chart(fig, use_container_width=True)

        status_counts = (
            orders.groupby("order_status", as_index=False)
            .agg(orders=("order_id", "size"))
        )

        st.subheader("Selected order statuses")
        show_table(status_counts)

    with sales:
        st.subheader("Product category performance")

        fig = px.bar(
            categories,
            x="merchandise_revenue",
            y="category",
            orientation="h",
            title="Category merchandise revenue",
            labels={
                "merchandise_revenue": "Merchandise revenue (INR)",
                "category": "Category",
            },
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

        display_categories = categories.copy()
        denominator = display_categories["merchandise_revenue"].replace(
            0, float("nan")
        )
        display_categories["item_profit_margin_pct"] = (
            100 * display_categories["item_profit"] / denominator
        ).round(2)

        show_table(display_categories.round(2))

        st.caption(
            "An order can contain multiple categories. "
            "Do not sum orders_containing_category to count unique orders."
        )

        state_sales = (
            orders.groupby("delivery_state", as_index=False)
            .agg(
                orders=("order_id", "size"),
                merchandise_revenue=("merchandise_revenue", "sum"),
                item_profit=("item_profit", "sum"),
            )
            .sort_values("merchandise_revenue", ascending=False)
        )

        st.subheader("Delivery-state performance")
        show_table(state_sales.round(2))

    with customers:
        customer_summary = (
            orders.groupby("customer_id", as_index=False)
            .agg(
                selected_orders=("order_id", "size"),
                selected_order_value=("final_amount", "sum"),
                last_selected_order_date=("order_date", "max"),
            )
        )

        purchaser_count = len(customer_summary)
        repeat_count = int(
            customer_summary["selected_orders"].ge(2).sum()
        )

        a, b, c = st.columns(3)
        a.metric("Customers in selection", f"{purchaser_count:,}")
        b.metric("Repeat customers in selection", f"{repeat_count:,}")
        c.metric(
            "Repeat-customer share",
            f"{100 * repeat_count / purchaser_count:.2f}%",
        )

        st.caption(
            "Repeat means at least two orders inside the current "
            "filtered selection, not lifetime repeat purchasing."
        )

        st.subheader("Top 20 customers in selection")
        top_customers = customer_summary.sort_values(
            "selected_order_value",
            ascending=False,
        ).head(20)

        show_table(top_customers)

        segment_summary = (
            orders.groupby("customer_segment", as_index=False)
            .agg(
                customers=("customer_id", "nunique"),
                orders=("order_id", "size"),
                selected_order_value=("final_amount", "sum"),
            )
        )

        st.subheader("Dataset customer segments")
        show_table(segment_summary.round(2))
        st.caption(
            "These segments are supplied synthetic simulation labels, "
            "not segments learned by this dashboard."
        )

    with operations:
        st.info(
            "Operations are linked to the selected order cohort. "
            "The date filter applies to order_date."
        )

        shipped = orders.loc[orders["shipment_id"].notna()].copy()
        recorded_deliveries = shipped.loc[
            shipped["actual_delivery_date"].notna()
        ].copy()

        boundary_count = int(
            recorded_deliveries["possible_year_end_clipping"]
            .fillna(0)
            .sum()
        )

        a, b, c = st.columns(3)
        a.metric("Linked shipment records", f"{len(shipped):,}")
        b.metric(
            "With recorded delivery dates",
            f"{len(recorded_deliveries):,}",
        )
        c.metric("Possible boundary-affected records", f"{boundary_count:,}")

        st.warning(
            "The source has 910 shipment-duration discrepancies overall. "
            "All match a possible year-end-clipping pattern. "
            "Recorded-date duration and delay analysis may be affected."
        )

        exclude_boundary = st.checkbox(
            "Exclude possible year-end-clipping records from "
            "duration and delay metrics",
            value=True,
        )

        duration_scope = recorded_deliveries.copy()

        if exclude_boundary:
            duration_scope = duration_scope.loc[
                duration_scope["possible_year_end_clipping"].eq(0)
            ]

        st.caption(
            f"Duration/delay denominator: {len(duration_scope):,} "
            "shipments with recorded delivery dates after this option."
        )

        if duration_scope.empty:
            st.info("No eligible shipment records for these metrics.")
        else:
            a, b = st.columns(2)
            a.metric(
                "Average recorded-date delivery days",
                f"{duration_scope['delivery_days_calculated'].mean():.2f}",
            )
            b.metric(
                "Recorded-date delay rate",
                f"{100 * duration_scope['delayed_flag'].mean():.2f}%",
            )

        shipment_status = (
            shipped.groupby("delivery_status", as_index=False)
            .agg(shipments=("shipment_id", "size"))
        )

        st.subheader("Linked shipment outcomes")
        show_table(shipment_status)

        orders_with_returns = int(
            orders["return_records"].gt(0).sum()
        )

        a, b = st.columns(2)
        a.metric(
            "Linked return records",
            f"{int(orders['return_records'].sum()):,}",
        )
        b.metric(
            "Orders with any return record",
            f"{orders_with_returns:,}",
        )

        st.caption(
            "Includes return records of every status. "
            "This is not a completed-return rate."
        )

    with st.expander("Metric definitions and limitations"):
        st.markdown(
            """
- All tabs follow the same selected order cohort.
- Empty multiselect filters mean all values.
- Order value includes tax and shipping.
- Merchandise revenue and item profit come from order items.
- Item profit is not net profit.
- Repeat-customer share is calculated within the selection.
- Shipment duration uses recorded dates.
- Boundary-affected shipment records are flagged.
- Customer segments are synthetic source labels.
- The dataset is simulated, not actual company performance.
- Gemini is not connected in this phase.
            """
        )

    st.download_button(
        "Download selected order cohort as CSV",
        data=orders.to_csv(index=False).encode("utf-8"),
        file_name="selected_order_cohort.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()