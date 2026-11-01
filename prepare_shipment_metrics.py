from pathlib import Path
import json

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "processed" / "shipments.csv"
OUTPUT_DIR = ROOT / "data" / "analysis_ready"
REPORT_DIR = ROOT / "reports" / "phase_2"

CUTOFF = pd.Timestamp("2025-12-31")


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing file: {SOURCE}")

    df = pd.read_csv(
        SOURCE,
        keep_default_na=False,
        na_values=[""],
        low_memory=False,
    )

    required = {
        "shipment_id",
        "dispatch_date",
        "expected_delivery_date",
        "actual_delivery_date",
        "delivery_days",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    for column in [
        "dispatch_date",
        "expected_delivery_date",
        "actual_delivery_date",
    ]:
        df[column] = pd.to_datetime(
            df[column],
            format="%Y-%m-%d",
            errors="raise",
        )

    stored = pd.to_numeric(df["delivery_days"], errors="raise")

    calculated = (
        df["actual_delivery_date"] - df["dispatch_date"]
    ).dt.days.astype("Int64")

    comparable = stored.notna() & calculated.notna()

    matches = pd.Series(False, index=df.index)

    matches.loc[comparable] = np.isclose(
        stored.loc[comparable].to_numpy(dtype=float),
        calculated.loc[comparable].to_numpy(dtype=float),
        atol=0,
        rtol=0,
    )

    mismatch = comparable & ~matches

    null_mismatch = stored.isna() != calculated.isna()

    implied_delivery_date = (
        df["dispatch_date"]
        + pd.to_timedelta(stored, unit="D")
    )

    possible_clipping = (
        mismatch
        & df["actual_delivery_date"].eq(CUTOFF)
        & implied_delivery_date.gt(CUTOFF)
    )

    df["delivery_days_calculated"] = calculated

    df["delivery_days_mismatch"] = (
        mismatch | null_mismatch
    ).astype("boolean")

    df["possible_year_end_clipping"] = (
        possible_clipping.astype("boolean")
    )

    mismatch_count = int(mismatch.sum())
    clipping_count = int(possible_clipping.sum())

    summary = {
        "shipments": len(df),
        "comparable_rows": int(comparable.sum()),
        "duration_mismatches": mismatch_count,
        "duration_null_mismatches": int(null_mismatch.sum()),
        "mismatches_matching_year_end_pattern": clipping_count,
        "other_duration_mismatches": int(
            (mismatch & ~possible_clipping).sum()
        ),
        "all_duration_mismatches_match_pattern": (
            bool(clipping_count == mismatch_count)
            if mismatch_count
            else None
        ),
        "source_file_modified": False,
        "interpretation": (
            "The flag identifies a pattern consistent with date clipping; "
            "it does not establish the generator's implementation."
        ),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    df.to_csv(
        OUTPUT_DIR / "shipments_enriched.csv",
        index=False,
        date_format="%Y-%m-%d",
    )

    evidence = df.loc[mismatch | null_mismatch].copy()

    evidence["implied_date_from_stored_days"] = (
        implied_delivery_date.loc[evidence.index]
    )

    evidence.to_csv(
        REPORT_DIR / "shipment_duration_diagnostics.csv",
        index=False,
        date_format="%Y-%m-%d",
    )

    with (REPORT_DIR / "shipment_duration_summary.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(summary, file, indent=2)

    print(json.dumps(summary, indent=2))
    print("\nSaved data/analysis_ready/shipments_enriched.csv")
    print("Original raw and processed files were not changed.")


if __name__ == "__main__":
    main()