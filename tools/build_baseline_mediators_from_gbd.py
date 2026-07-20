#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build stratum-resolved sodium and SBP mediator baselines from GBD 2023.

The authenticated IHME inputs are development-only files under ``data/raw``.
This tool emits the compact, adapted ``baseline_mediators.csv`` bundled with
the package.  The GBD ``lower`` and ``upper`` fields are uncertainty bounds on
the modeled stratum mean; they are not within-stratum exposure quantiles or an
estimate of the usual-SBP standard deviation.

Run from the repository root::

    python -m tools.build_baseline_mediators_from_gbd
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from tools.dietary_exposure_sources import (
    ADULT_AGE_START,
    LOCATION_HIERARCHY_PATH,
    MANIFEST_PATH,
    MEDIATOR_SOURCES,
    MODEL_AGE,
    RAW_DIR,
    REFERENCE_YEAR,
    ExposureSource,
    ensure_location_hierarchy,
    national_locations,
    read_exposure,
    read_manifest,
    select_exposure_cells,
)

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "src" / "mealhealth" / "data" / "baseline_mediators.csv"


def _select_source_cells(
    frame: pd.DataFrame,
    *,
    prefix: str,
    locations: pd.DataFrame,
    source_countries: set[str],
) -> pd.DataFrame:
    selected = select_exposure_cells(
        frame,
        label=prefix,
        locations=locations,
        source_countries=source_countries,
    )
    return selected.rename(
        columns={
            "mean": f"{prefix}_mean",
            "lower": f"{prefix}_lower",
            "upper": f"{prefix}_upper",
        }
    )


def build_baseline_mediators(
    *,
    raw_dir: Path = RAW_DIR,
    manifest_path: Path = MANIFEST_PATH,
    location_hierarchy_path: Path | None = None,
    sodium_source: ExposureSource = MEDIATOR_SOURCES["sodium_urinary"],
    sbp_source: ExposureSource = MEDIATOR_SOURCES["sbp"],
    verify_checksum: bool = True,
    expected_country_count: int | None = 175,
) -> pd.DataFrame:
    """Return exact 2020 country-age-sex sodium and SBP mean exposures."""

    location_hierarchy_path = location_hierarchy_path or (
        raw_dir / LOCATION_HIERARCHY_PATH.name
    )
    ensure_location_hierarchy(location_hierarchy_path)
    manifest = read_manifest(
        manifest_path, expected_country_count=expected_country_count
    )
    source_by_country = dict(
        zip(
            manifest["country"],
            manifest["gbd_exposure_source_country"],
            strict=True,
        )
    )
    source_countries = set(source_by_country.values())
    locations = national_locations(location_hierarchy_path)
    sodium = _select_source_cells(
        read_exposure(sodium_source, raw_dir=raw_dir, verify_checksum=verify_checksum),
        prefix="sodium_urinary_g_per_day",
        locations=locations,
        source_countries=source_countries,
    )
    sbp = _select_source_cells(
        read_exposure(sbp_source, raw_dir=raw_dir, verify_checksum=verify_checksum),
        prefix="sbp_mmhg",
        locations=locations,
        source_countries=source_countries,
    )
    key = ["source_country", "age_group_id", "sex_id"]
    source_rows = sodium.merge(sbp, on=key, how="inner", validate="one_to_one")
    expected_source_rows = len(source_countries) * len(ADULT_AGE_START) * 2
    if len(source_rows) != expected_source_rows:
        raise ValueError(
            f"Expected {expected_source_rows} source mediator rows, got "
            f"{len(source_rows)}"
        )

    rows = []
    by_source = source_rows.groupby("source_country", sort=False)
    for country, source_country in source_by_country.items():
        country_rows = by_source.get_group(source_country).copy()
        country_rows.insert(0, "country", country)
        rows.append(country_rows)
    output = pd.concat(rows, ignore_index=True)
    output["age"] = output["age_group_id"].map(MODEL_AGE)
    output["sex"] = output["sex_id"].map({1: "male", 2: "female"})
    output["source_year"] = REFERENCE_YEAR
    columns = [
        "country",
        "age",
        "sex",
        "sodium_urinary_g_per_day_mean",
        "sodium_urinary_g_per_day_lower",
        "sodium_urinary_g_per_day_upper",
        "sbp_mmhg_mean",
        "sbp_mmhg_lower",
        "sbp_mmhg_upper",
        "source_country",
        "source_year",
    ]
    output = output.sort_values(["country", "age_group_id", "sex_id"])[columns]
    if output.duplicated(["country", "age", "sex"]).any():
        raise ValueError("Duplicate country-age-sex mediator rows")
    return output.reset_index(drop=True)


def write_baseline_mediators(frame: pd.DataFrame, output: Path = OUT_PATH) -> None:
    """Write a byte-stable bundled mediator baseline."""

    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False, float_format="%.10g", lineterminator="\n")


def build_and_write_baseline_mediators(
    *,
    raw_dir: Path = RAW_DIR,
    output: Path = OUT_PATH,
    verify_checksum: bool = True,
) -> pd.DataFrame:
    """Build and write the sodium/SBP mediator baseline."""

    frame = build_baseline_mediators(raw_dir=raw_dir, verify_checksum=verify_checksum)
    write_baseline_mediators(frame, output)
    print(f"Wrote {len(frame)} rows to {output}")
    return frame


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output", type=Path, default=OUT_PATH)
    parser.add_argument("--no-checksum", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    build_and_write_baseline_mediators(
        raw_dir=args.raw_dir,
        output=args.output,
        verify_checksum=not args.no_checksum,
    )


if __name__ == "__main__":
    main()
