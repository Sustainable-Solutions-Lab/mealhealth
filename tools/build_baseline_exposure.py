#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build the complete direct exposure baseline from GBD 2023 files.

The output is the single direct-factor table consumed by :mod:`mealhealth`;
the sodium/SBP mediator remains a separate stratum-resolved table.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from tools.dietary_exposure_sources import (
    ADULT_AGE_START,
    BASIS_FACTORS,
    DIRECT_SOURCES,
    MANIFEST_PATH,
    REFERENCE_YEAR,
    WPP_POPULATION_PATH,
    ensure_location_hierarchy,
    national_locations,
    read_exposure,
    read_manifest,
    wpp_age_sex_weights,
)

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "src" / "mealhealth" / "data" / "baseline_exposure.csv"


def build_baseline_exposure(
    *,
    manifest_path: Path = MANIFEST_PATH,
    location_hierarchy_path: Path | None = None,
    wpp_path: Path = WPP_POPULATION_PATH,
    verify_checksum: bool = True,
) -> pd.DataFrame:
    manifest = read_manifest(manifest_path)
    location_hierarchy_path = location_hierarchy_path or (
        ROOT / "data" / "raw" / "IHME_GBD_2021_A1_HIERARCHIES_Y2024M05D15.XLSX"
    )
    if (
        not location_hierarchy_path.exists()
        and not (ROOT / "data" / "raw" / "IHME-GBD_2023-death-rates-2020.csv").exists()
    ):
        ensure_location_hierarchy(location_hierarchy_path)
    locations = national_locations(location_hierarchy_path)
    source_countries = set(manifest["gbd_exposure_source_country"])
    weights = wpp_age_sex_weights(source_countries, wpp_path)
    rows: list[pd.DataFrame] = []
    for risk_factor, source in DIRECT_SOURCES.items():
        frame = read_exposure(source, verify_checksum=verify_checksum)
        frame = frame[
            (frame["year_id"] == REFERENCE_YEAR)
            & frame["age_group_id"].isin(ADULT_AGE_START)
        ].merge(locations, on="location_id", how="inner", validate="many_to_one")
        frame = frame[frame["source_country"].isin(source_countries)].copy()
        key = ["source_country", "age_group_id", "sex_id"]
        if frame.duplicated(key).any():
            raise ValueError(f"Duplicate {risk_factor} GBD age-sex cells")
        missing = source_countries - set(frame["source_country"])
        if missing:
            raise ValueError(f"GBD {risk_factor} exposure missing: {sorted(missing)}")
        merged = frame.merge(weights, on=key, how="left", validate="one_to_one")
        if merged["population"].isna().any():
            raise ValueError(f"Missing WPP weight for {risk_factor}")
        merged["weighted"] = merged["mean"] * merged["population"]
        aggregate = merged.groupby("source_country", as_index=False).agg(
            weighted=("weighted", "sum"), population=("population", "sum")
        )
        aggregate["exposure_g_per_day"] = (
            aggregate["weighted"] / aggregate["population"] * BASIS_FACTORS[risk_factor]
        )
        values = dict(
            zip(
                aggregate["source_country"],
                aggregate["exposure_g_per_day"],
                strict=True,
            )
        )
        out = manifest[["country", "gbd_exposure_source_country"]].copy()
        out["risk_factor"] = risk_factor
        out["exposure_g_per_day"] = out["gbd_exposure_source_country"].map(values)
        out["source_country"] = out["gbd_exposure_source_country"]
        out["source_year"] = REFERENCE_YEAR
        rows.append(
            out[
                [
                    "country",
                    "risk_factor",
                    "exposure_g_per_day",
                    "source_country",
                    "source_year",
                ]
            ]
        )
    output = (
        pd.concat(rows, ignore_index=True)
        .sort_values(["country", "risk_factor"])
        .reset_index(drop=True)
    )
    if len(output) != len(manifest) * len(DIRECT_SOURCES) or output.isna().any().any():
        raise ValueError("Direct exposure output is incomplete")
    if (
        not np.isfinite(output["exposure_g_per_day"]).all()
        or (output["exposure_g_per_day"] < 0).any()
    ):
        raise ValueError("Direct exposure baselines must be finite and non-negative")
    return output


def write_baseline_exposure(frame: pd.DataFrame, output: Path = OUT_PATH) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False, float_format="%.10g", lineterminator="\n")


def build_and_write_baseline_exposure(
    *,
    manifest_path: Path = MANIFEST_PATH,
    output: Path = OUT_PATH,
    verify_checksum: bool = True,
) -> pd.DataFrame:
    """Build and write the direct exposure baseline."""

    frame = build_baseline_exposure(
        manifest_path=manifest_path, verify_checksum=verify_checksum
    )
    write_baseline_exposure(frame, output)
    print(f"Wrote {len(frame)} rows to {output}")
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=OUT_PATH)
    parser.add_argument("--no-checksum", action="store_true")
    args = parser.parse_args()
    build_and_write_baseline_exposure(
        manifest_path=args.manifest,
        output=args.output,
        verify_checksum=not args.no_checksum,
    )


if __name__ == "__main__":
    main()
