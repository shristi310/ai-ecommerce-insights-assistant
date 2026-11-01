from pathlib import Path
import json

import pandas as pd


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports" / "phase_2"

PRIMARY_KEYS = {
    "customers": "customer_id",
    "products": "product_id",
    "orders": "order_id",
    "order_items": "order_item_id",
    "payments": "payment_id",
    "shipments": "shipment_id",
    "returns": "return_id",
    "customer_reviews": "review_id",
    "marketing_campaigns": "campaign_id",
}

RELATIONSHIPS = [
    ("orders", "customer_id", "customers", "customer_id"),
    ("orders", "campaign_id", "marketing_campaigns", "campaign_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("payments", "order_id", "orders", "order_id"),
    ("shipments", "order_id", "orders", "order_id"),
    ("returns", "order_id", "orders", "order_id"),
    ("returns", "customer_id", "customers", "customer_id"),
    ("returns", "product_id", "products", "product_id"),
    ("customer_reviews", "order_id", "orders", "order_id"),
    ("customer_reviews", "customer_id", "customers", "customer_id"),
    ("customer_reviews", "product_id", "products", "product_id"),
]


def read_text_csv(path):
    return pd.read_csv(
        path,
        dtype="string",
        keep_default_na=False,
        encoding="utf-8-sig",
    )


def convert_column(series, data_type, label):
    values = series.str.strip()
    values = values.mask(values.eq(""), pd.NA)

    dtype = data_type.strip().lower()

    if dtype == "date":
        converted = pd.to_datetime(
            values,
            format="%Y-%m-%d",
            errors="coerce",
        )

    elif dtype.startswith("int") or dtype == "float":
        converted = pd.to_numeric(values, errors="coerce")

    elif dtype == "bool":
        converted = values.str.lower().map(
            {"true": True, "false": False}
        ).astype("boolean")

    elif dtype == "string":
        return values

    else:
        raise ValueError(
            f"{label}: unsupported dictionary type {data_type!r}"
        )

    invalid = values.notna() & converted.isna()

    if invalid.any():
        examples = values[invalid].head(5).tolist()
        raise ValueError(
            f"{label}: {invalid.sum()} invalid values. "
            f"Examples: {examples}"
        )

    if dtype.startswith("int"):
        non_integer = converted.notna() & converted.mod(1).ne(0)

        if non_integer.any():
            raise ValueError(f"{label}: non-integer numeric values")

        converted = converted.astype("Int64")

    elif dtype == "float":
        converted = converted.astype("Float64")

    return converted


def main():
    dictionary_path = RAW / "data_dictionary.csv"

    if not dictionary_path.exists():
        raise FileNotFoundError(
            "Missing data/raw/data_dictionary.csv"
        )

    dictionary = read_text_csv(dictionary_path)

    required_fields = {
        "table_name",
        "column_name",
        "data_type",
        "nullable",
    }

    if not required_fields.issubset(dictionary.columns):
        raise ValueError("Data dictionary is missing required columns.")

    for field in required_fields:
        dictionary[field] = dictionary[field].str.strip()

    if dictionary.duplicated(["table_name", "column_name"]).any():
        raise ValueError("Dictionary contains duplicate column definitions.")

    expected_tables = set(PRIMARY_KEYS)
    documented_tables = set(dictionary["table_name"])

    if documented_tables != expected_tables:
        raise ValueError(
            "Unexpected dictionary table list. "
            f"Found: {sorted(documented_tables)}"
        )

    tables = {}
    summary = []

    # Validate and convert every table before exporting any new CSV.
    for table, primary_key in PRIMARY_KEYS.items():
        path = RAW / f"{table}.csv"

        if not path.exists():
            raise FileNotFoundError(f"Missing file: {path.name}")

        df = read_text_csv(path)

        specs = dictionary.loc[
            dictionary["table_name"].eq(table)
        ]

        expected_columns = specs["column_name"].tolist()
        missing = sorted(set(expected_columns) - set(df.columns))
        extra = sorted(set(df.columns) - set(expected_columns))

        if missing or extra:
            raise ValueError(
                f"{table}: missing columns={missing}; "
                f"extra columns={extra}"
            )

        rows_before = len(df)

        for spec in specs.to_dict("records"):
            column = spec["column_name"]

            df[column] = convert_column(
                df[column],
                spec["data_type"],
                f"{table}.{column}",
            )

            nullable = spec["nullable"].lower().startswith("yes")

            if not nullable and df[column].isna().any():
                raise ValueError(
                    f"{table}.{column}: unexpected missing values"
                )

        if df[primary_key].isna().any():
            raise ValueError(f"{table}: missing primary key")

        if df[primary_key].duplicated().any():
            raise ValueError(f"{table}: duplicate primary key")

        tables[table] = df

        summary.append(
            {
                "table": table,
                "rows_before": rows_before,
                "rows_after": len(df),
                "missing_cells": int(df.isna().sum().sum()),
                "primary_key": primary_key,
            }
        )

    fk_results = []

    for child, child_column, parent, parent_column in RELATIONSHIPS:
        values = tables[child][child_column]
        parent_values = tables[parent][parent_column]

        invalid = values.notna() & ~values.isin(parent_values)
        invalid_count = int(invalid.sum())

        fk_results.append(
            {
                "relationship": (
                    f"{child}.{child_column} -> "
                    f"{parent}.{parent_column}"
                ),
                "invalid_rows": invalid_count,
            }
        )

    REPORTS.mkdir(parents=True, exist_ok=True)

    with (REPORTS / "foreign_key_checks.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(fk_results, file, indent=2)

    if any(result["invalid_rows"] for result in fk_results):
        raise ValueError(
            "Foreign-key errors found. No new processed CSVs exported. "
            "Review reports/phase_2/foreign_key_checks.json."
        )

    PROCESSED.mkdir(parents=True, exist_ok=True)

    for table, df in tables.items():
        df.to_csv(
            PROCESSED / f"{table}.csv",
            index=False,
            date_format="%Y-%m-%d",
        )

    pd.DataFrame(summary).to_csv(
        REPORTS / "cleaning_summary.csv",
        index=False,
    )

    print("\nSchema, type, nullability, and key checks passed.")
    print(pd.DataFrame(summary).to_string(index=False))
    print("\nProcessed CSVs saved in data/processed/.")
    print("Business-rule validation is still pending.")


if __name__ == "__main__":
    main()