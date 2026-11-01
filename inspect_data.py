from pathlib import Path
import json
import re

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
REPORT_DIR = PROJECT_ROOT / "reports" / "phase_2"


def proposed_column_name(column):
    name = str(column).strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def inspect_file(file_path):
    # Preserve original text; do not interpret strings such as "NA" as missing.
    raw_df = pd.read_csv(
        file_path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    inferred_df = pd.read_csv(
        file_path,
        low_memory=False,
        encoding="utf-8-sig",
    )

    row_count = len(raw_df)
    column_records = []
    candidate_keys = []

    for column in raw_df.columns:
        original = raw_df[column]
        trimmed = original.str.strip()
        blank = trimmed.eq("")

        nonblank_unique = trimmed.loc[~blank].nunique()
        duplicate_nonblank_rows = trimmed.loc[~blank].duplicated().sum()
        whitespace_rows = original.ne(trimmed).sum()

        normalized_name = proposed_column_name(column)
        id_like = (
            normalized_name == "id"
            or normalized_name.endswith("_id")
        )

        unique_nonblank = (
            row_count > 0
            and not blank.any()
            and nonblank_unique == row_count
        )

        if id_like and unique_nonblank:
            candidate_keys.append(str(column))

        column_records.append(
            {
                "file": file_path.name,
                "column": str(column),
                "proposed_column_name": normalized_name,
                "inferred_dtype": str(inferred_df[column].dtype),
                "blank_cells": int(blank.sum()),
                "pandas_detected_missing": int(
                    inferred_df[column].isna().sum()
                ),
                "unique_nonblank_values": int(nonblank_unique),
                "duplicate_nonblank_rows": int(
                    duplicate_nonblank_rows
                ),
                "outer_whitespace_rows": int(whitespace_rows),
                "id_like_name": bool(id_like),
                "unique_and_nonblank": bool(unique_nonblank),
            }
        )

    proposed_names = [
        proposed_column_name(column)
        for column in raw_df.columns
    ]

    name_collisions = sorted(
        {
            name
            for name in proposed_names
            if proposed_names.count(name) > 1
        }
    )

    summary = {
        "file": file_path.name,
        "size_mb": round(file_path.stat().st_size / (1024 ** 2), 3),
        "rows": row_count,
        "columns": len(raw_df.columns),
        "exact_duplicate_rows": int(raw_df.duplicated().sum()),
        "candidate_primary_keys": ", ".join(candidate_keys),
        "proposed_name_collisions": ", ".join(name_collisions),
    }

    return summary, column_records


def main():
    if not RAW_DIR.exists():
        raise SystemExit(
            f"Raw data folder does not exist: {RAW_DIR}"
        )

    csv_files = sorted(
        path
        for path in RAW_DIR.iterdir()
        if path.is_file() and path.suffix.lower() == ".csv"
    )

    if not csv_files:
        raise SystemExit(
            "No CSV files found directly inside data/raw/. "
            "Extract the ZIP and place the CSVs there."
        )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    summaries = []
    columns = []
    errors = []

    for file_path in csv_files:
        print(f"Inspecting: {file_path.name}")

        try:
            summary, column_records = inspect_file(file_path)
            summaries.append(summary)
            columns.extend(column_records)
        except Exception as error:
            errors.append(
                {
                    "file": file_path.name,
                    "error": str(error),
                }
            )

    summary_df = pd.DataFrame(summaries)
    columns_df = pd.DataFrame(columns)

    summary_df.to_csv(
        REPORT_DIR / "file_summary.csv",
        index=False,
    )

    columns_df.to_csv(
        REPORT_DIR / "column_summary.csv",
        index=False,
    )

    with (REPORT_DIR / "read_errors.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(errors, file, indent=2, ensure_ascii=False)

    report_lines = [
        "PHASE 2 — DATASET INSPECTION",
        "",
        f"CSV files found: {len(csv_files)}",
        f"Successfully inspected: {len(summaries)}",
        f"Files with errors: {len(errors)}",
        "",
    ]

    for summary in summaries:
        report_lines.extend(
            [
                "=" * 75,
                f"FILE: {summary['file']}",
                f"Rows: {summary['rows']:,}",
                f"Columns: {summary['columns']}",
                (
                    "Exact duplicate rows: "
                    f"{summary['exact_duplicate_rows']:,}"
                ),
                (
                    "Candidate primary keys: "
                    f"{summary['candidate_primary_keys'] or 'None detected'}"
                ),
                (
                    "Proposed column-name collisions: "
                    f"{summary['proposed_name_collisions'] or 'None'}"
                ),
                "",
            ]
        )

        file_columns = columns_df[
            columns_df["file"] == summary["file"]
        ]

        report_lines.append(
            file_columns[
                [
                    "column",
                    "inferred_dtype",
                    "blank_cells",
                    "unique_nonblank_values",
                    "outer_whitespace_rows",
                ]
            ].to_string(index=False)
        )

        report_lines.append("")

    if errors:
        report_lines.append("READ ERRORS")
        report_lines.append(
            json.dumps(errors, indent=2, ensure_ascii=False)
        )

    report_lines.extend(
        [
            "",
            "NOTES",
            "- Raw CSV files were not modified.",
            "- Candidate keys require manual confirmation.",
            "- No foreign-key relationships have been verified yet.",
            "- No rows were removed or missing values filled.",
            "- No dates, prices, or business metrics were transformed.",
        ]
    )

    report_text = "\n".join(report_lines)

    (REPORT_DIR / "inspection_report.txt").write_text(
        report_text,
        encoding="utf-8",
    )

    print("\nInspection finished.")
    print(f"Reports saved to: {REPORT_DIR}")
    print(f"Successfully inspected: {len(summaries)}")
    print(f"Files with errors: {len(errors)}")

    if errors:
        print("Review read_errors.json before continuing.")


if __name__ == "__main__":
    main()