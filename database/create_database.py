from pathlib import Path
import argparse
import json
import math
import os
import re
import sqlite3

import pandas as pd

from contextlib import closing


ROOT = Path(__file__).resolve().parents[1]

PROCESSED = ROOT / "data" / "processed"
DICTIONARY = ROOT / "data" / "raw" / "data_dictionary.csv"
ENRICHED_SHIPMENTS = (
    ROOT / "data" / "analysis_ready" / "shipments_enriched.csv"
)

DATABASE_DIR = ROOT / "database"
DATABASE_PATH = DATABASE_DIR / "ecommerce.db"
TEMP_DATABASE_PATH = DATABASE_DIR / "ecommerce.build.db"
SCHEMA_PATH = DATABASE_DIR / "schema.sql"
REPORT_DIR = ROOT / "reports" / "phase_3"

# Parent tables come before dependent tables.
TABLE_ORDER = [
    "customers",
    "products",
    "marketing_campaigns",
    "orders",
    "order_items",
    "payments",
    "shipments",
    "returns",
    "customer_reviews",
]

PRIMARY_KEYS = {
    "customers": "customer_id",
    "products": "product_id",
    "marketing_campaigns": "campaign_id",
    "orders": "order_id",
    "order_items": "order_item_id",
    "payments": "payment_id",
    "shipments": "shipment_id",
    "returns": "return_id",
    "customer_reviews": "review_id",
}

FOREIGN_KEYS = {
    "orders": [
        ("customer_id", "customers", "customer_id"),
        ("campaign_id", "marketing_campaigns", "campaign_id"),
    ],
    "order_items": [
        ("order_id", "orders", "order_id"),
        ("product_id", "products", "product_id"),
    ],
    "payments": [
        ("order_id", "orders", "order_id"),
    ],
    "shipments": [
        ("order_id", "orders", "order_id"),
    ],
    "returns": [
        ("order_id", "orders", "order_id"),
        ("customer_id", "customers", "customer_id"),
        ("product_id", "products", "product_id"),
    ],
    "customer_reviews": [
        ("order_id", "orders", "order_id"),
        ("customer_id", "customers", "customer_id"),
        ("product_id", "products", "product_id"),
    ],
}

SHIPMENT_EXTRA_COLUMNS = [
    {
        "column_name": "delivery_days_calculated",
        "data_type": "int",
        "nullable": "Yes",
    },
    {
        "column_name": "delivery_days_mismatch",
        "data_type": "bool",
        "nullable": "No",
    },
    {
        "column_name": "possible_year_end_clipping",
        "data_type": "bool",
        "nullable": "No",
    },
]

EXTRA_INDEXES = {
    "customers": ["state", "customer_segment"],
    "products": ["category"],
    "orders": ["order_date", "order_status"],
    "payments": ["payment_status"],
    "shipments": ["delivery_status"],
    "returns": ["return_date"],
    "customer_reviews": ["review_date"],
}


def quote_identifier(value):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise ValueError(f"Unexpected SQL identifier: {value!r}")

    return f'"{value}"'


def sqlite_type(data_type):
    dtype = data_type.strip().lower()

    if dtype.startswith("int") or dtype == "bool":
        return "INTEGER"

    if dtype == "float":
        return "REAL"

    if dtype in {"string", "date"}:
        return "TEXT"

    raise ValueError(f"Unsupported dictionary type: {data_type!r}")


def get_specs():
    if not DICTIONARY.exists():
        raise FileNotFoundError(f"Missing dictionary: {DICTIONARY}")

    dictionary = pd.read_csv(
        DICTIONARY,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    required = {"table_name", "column_name", "data_type", "nullable"}

    if not required.issubset(dictionary.columns):
        raise ValueError("Dictionary is missing required fields.")

    for column in required:
        dictionary[column] = dictionary[column].str.strip()

    if dictionary.duplicated(["table_name", "column_name"]).any():
        raise ValueError("Duplicate dictionary column definitions.")

    if set(dictionary["table_name"]) != set(TABLE_ORDER):
        raise ValueError("Dictionary table list does not match this project.")

    specs = {}

    for table in TABLE_ORDER:
        records = dictionary.loc[
            dictionary["table_name"].eq(table),
            ["column_name", "data_type", "nullable"],
        ].to_dict("records")

        if table == "shipments":
            records.extend(SHIPMENT_EXTRA_COLUMNS)

        names = [record["column_name"] for record in records]

        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate schema columns for {table}")

        for name in names:
            quote_identifier(name)

        specs[table] = records

    return specs


def source_path(table):
    if table == "shipments":
        return ENRICHED_SHIPMENTS

    return PROCESSED / f"{table}.csv"


def read_source(table, specs):
    path = source_path(table)

    if not path.exists():
        raise FileNotFoundError(f"Missing source file: {path}")

    frame = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    expected = [spec["column_name"] for spec in specs]
    missing = sorted(set(expected) - set(frame.columns))
    extra = sorted(set(frame.columns) - set(expected))

    if missing or extra:
        raise ValueError(
            f"{table}: missing columns={missing}; extra columns={extra}"
        )

    return frame[expected]


def convert_value(value, spec):
    nullable = spec["nullable"].strip().lower().startswith("yes")
    dtype = spec["data_type"].strip().lower()

    if value == "":
        if not nullable:
            raise ValueError("Unexpected blank in required column")
        return None

    if dtype == "string":
        return value

    if dtype == "date":
        parsed = pd.Timestamp(value)

        if pd.isna(parsed):
            raise ValueError("Invalid date")

        if parsed.strftime("%Y-%m-%d") != value:
            raise ValueError(f"Expected YYYY-MM-DD date, got {value!r}")

        return value

    if dtype == "bool":
        mapping = {
            "true": 1,
            "false": 0,
            "1": 1,
            "0": 0,
        }

        key = value.lower()

        if key not in mapping:
            raise ValueError(f"Invalid Boolean: {value!r}")

        return mapping[key]

    number = float(value)

    if not math.isfinite(number):
        raise ValueError("Non-finite number")

    if dtype.startswith("int"):
        if not number.is_integer():
            raise ValueError(f"Expected integer, got {value!r}")
        return int(number)

    if dtype == "float":
        return number

    raise ValueError(f"Unsupported type: {dtype}")


def converted_rows(table, frame, specs):
    for row_number, row in enumerate(
        frame.itertuples(index=False, name=None),
        start=2,
    ):
        converted = []

        for value, spec in zip(row, specs):
            try:
                converted.append(convert_value(value, spec))
            except Exception as error:
                raise ValueError(
                    f"{table}, CSV row {row_number}, "
                    f"column {spec['column_name']}: {error}"
                ) from error

        yield tuple(converted)


def make_schema(specs):
    statements = [
        "-- Generated by database/create_database.py",
        "-- Source dates are stored as ISO YYYY-MM-DD text.",
        "-- Monetary values use REAL for this analytics portfolio.",
        "PRAGMA foreign_keys = ON;",
    ]

    for table in TABLE_ORDER:
        definitions = []
        primary_key = PRIMARY_KEYS[table]

        for spec in specs[table]:
            column = spec["column_name"]
            q_column = quote_identifier(column)
            dtype = sqlite_type(spec["data_type"])

            definition = f"{q_column} {dtype}"

            if column == primary_key:
                definition += " PRIMARY KEY NOT NULL"
            elif not spec["nullable"].lower().startswith("yes"):
                definition += " NOT NULL"

            if spec["data_type"].lower() == "bool":
                definition += f" CHECK ({q_column} IN (0, 1))"

            definitions.append(definition)

        for child_column, parent, parent_column in FOREIGN_KEYS.get(
            table, []
        ):
            definitions.append(
                f"FOREIGN KEY ({quote_identifier(child_column)}) "
                f"REFERENCES {quote_identifier(parent)} "
                f"({quote_identifier(parent_column)})"
            )

        # Observed one-payment and one-shipment-per-order structure.
        if table in {"payments", "shipments"}:
            definitions.append('UNIQUE ("order_id")')

        body = ",\n    ".join(definitions)

        statements.append(
            f"CREATE TABLE {quote_identifier(table)} (\n"
            f"    {body}\n"
            f") STRICT;"
        )

    return "\n\n".join(statements) + "\n"


def create_indexes(connection):
    for table in TABLE_ORDER:
        columns = set(EXTRA_INDEXES.get(table, []))

        for child_column, _, _ in FOREIGN_KEYS.get(table, []):
            columns.add(child_column)

        # UNIQUE(order_id) already supplies an index on these tables.
        if table in {"payments", "shipments"}:
            columns.discard("order_id")

        for column in sorted(columns):
            name = f"idx_{table}_{column}"

            connection.execute(
                f"CREATE INDEX {quote_identifier(name)} "
                f"ON {quote_identifier(table)} "
                f"({quote_identifier(column)})"
            )


def verify_database(path, specs):
    uri = path.resolve().as_uri() + "?mode=ro"

    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")

        integrity = [
            row[0]
            for row in connection.execute("PRAGMA integrity_check")
        ]

        if integrity != ["ok"]:
            raise ValueError(f"Integrity check failed: {integrity}")

        fk_errors = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if fk_errors:
            raise ValueError(
                f"Foreign-key check failed: {fk_errors[:5]}"
            )

        actual_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }

        if actual_tables != set(TABLE_ORDER):
            raise ValueError("Database table list is incorrect.")

        counts = {}

        for table in TABLE_ORDER:
            frame = read_source(table, specs[table])
            q_table = quote_identifier(table)

            database_rows = connection.execute(
                f"SELECT COUNT(*) FROM {q_table}"
            ).fetchone()[0]

            if database_rows != len(frame):
                raise ValueError(f"{table}: row-count mismatch")

            # Compare column types, nullability, and primary-key flags.
            info = connection.execute(
                f"PRAGMA table_info({q_table})"
            ).fetchall()

            expected_info = []

            for spec in specs[table]:
                column = spec["column_name"]
                is_pk = column == PRIMARY_KEYS[table]
                not_null = (
                    is_pk
                    or not spec["nullable"].lower().startswith("yes")
                )

                expected_info.append(
                    (
                        column,
                        sqlite_type(spec["data_type"]),
                        int(not_null),
                        int(is_pk),
                    )
                )

            actual_info = [
                (row[1], row[2], row[3], row[5])
                for row in info
            ]

            if actual_info != expected_info:
                raise ValueError(f"{table}: schema mismatch")

            # Compare missing-cell counts, column by column.
            null_expressions = [
                f"SUM({quote_identifier(spec['column_name'])} IS NULL)"
                for spec in specs[table]
            ]

            database_nulls = connection.execute(
                f"SELECT {', '.join(null_expressions)} FROM {q_table}"
            ).fetchone()

            for index, spec in enumerate(specs[table]):
                column = spec["column_name"]
                source_nulls = int(frame[column].eq("").sum())

                if (database_nulls[index] or 0) != source_nulls:
                    raise ValueError(
                        f"{table}.{column}: missing-value count mismatch"
                    )

            counts[table] = database_rows

        diagnostics = connection.execute(
            """
            SELECT
                SUM(delivery_days_mismatch),
                SUM(possible_year_end_clipping)
            FROM shipments
            """
        ).fetchone()

        # Confirm the accepted Phase 2 findings survived the load.
        if tuple(diagnostics) != (910, 910):
            raise ValueError(
                "Shipment diagnostic counts differ from Phase 2: "
                f"{diagnostics}"
            )

        index_count = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'index' AND name LIKE 'idx_%'"
        ).fetchone()[0]

    return {
        "status": "PASS",
        "integrity_check": "ok",
        "foreign_key_violations": 0,
        "table_count": len(counts),
        "row_counts": counts,
        "explicit_index_count": index_count,
        "shipment_duration_mismatches": int(diagnostics[0]),
        "possible_year_end_clipping": int(diagnostics[1]),
        "limitation": (
            "Verification covers structure, counts, null counts, "
            "constraints, and shipment diagnostic totals; it is not "
            "a full cell-by-cell comparison."
        ),
    }


def save_report(report):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    with (REPORT_DIR / "database_verification.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(report, file, indent=2)

    print(json.dumps(report, indent=2))


def build(specs):
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    if TEMP_DATABASE_PATH.exists():
        TEMP_DATABASE_PATH.unlink()

    schema = make_schema(specs)
    connection = None

    try:
        connection = sqlite3.connect(TEMP_DATABASE_PATH)
        connection.execute("PRAGMA foreign_keys = ON")

        if connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0] != 1:
            raise RuntimeError("Foreign-key enforcement was not enabled.")

        connection.executescript(schema)

        with connection:
            for table in TABLE_ORDER:
                frame = read_source(table, specs[table])
                columns = [
                    spec["column_name"]
                    for spec in specs[table]
                ]

                column_sql = ", ".join(
                    quote_identifier(column)
                    for column in columns
                )

                placeholders = ", ".join("?" for _ in columns)

                sql = (
                    f"INSERT INTO {quote_identifier(table)} "
                    f"({column_sql}) VALUES ({placeholders})"
                )

                connection.executemany(
                    sql,
                    converted_rows(table, frame, specs[table]),
                )

                print(f"Loaded {table}: {len(frame):,} rows")

            create_indexes(connection)

        connection.close()
        connection = None

        report = verify_database(TEMP_DATABASE_PATH, specs)

        # Replace the final database only after the new build passes.
        os.replace(TEMP_DATABASE_PATH, DATABASE_PATH)

        SCHEMA_PATH.write_text(schema, encoding="utf-8")
        save_report(report)

        print(f"\nDatabase ready: {DATABASE_PATH}")
        print("Raw and processed CSVs were not modified.")

    finally:
        if connection is not None:
            connection.close()

        if TEMP_DATABASE_PATH.exists():
            TEMP_DATABASE_PATH.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify the existing database without rebuilding it.",
    )
    args = parser.parse_args()

    if sqlite3.sqlite_version_info < (3, 37, 0):
        raise RuntimeError(
            "SQLite 3.37 or later is required for STRICT tables."
        )

    specs = get_specs()

    if args.verify:
        if not DATABASE_PATH.exists():
            raise FileNotFoundError("Build the database first.")

        save_report(verify_database(DATABASE_PATH, specs))
    else:
        build(specs)


if __name__ == "__main__":
    main()