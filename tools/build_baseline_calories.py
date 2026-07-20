#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build adult country calorie baselines from the public GDD-IA table."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from dietary_exposure_sources import (
        MANIFEST_PATH,
        REFERENCE_YEAR,
        WPP_POPULATION_PATH,
        read_manifest,
    )
except ModuleNotFoundError:  # importlib-based tests load this file as a module
    from tools.dietary_exposure_sources import (
        MANIFEST_PATH,
        REFERENCE_YEAR,
        WPP_POPULATION_PATH,
        read_manifest,
    )
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "data" / "raw" / "GDD-IA-intake_kcals_2020.csv"
OUT_PATH = ROOT / "src" / "mealhealth" / "data" / "baseline_calories.csv"


def _wpp_band_weights(countries: set[str], path: Path) -> pd.DataFrame:
    columns = ["ISO3_code", "Variant", "Time", "AgeGrpStart", "PopMale", "PopFemale"]
    frame = pd.read_csv(path, usecols=columns, low_memory=False)
    frame = frame[
        (frame["Variant"].astype(str).str.lower() == "medium")
        & (frame["Time"] == REFERENCE_YEAR)
        & frame["ISO3_code"].isin(countries)
    ].copy()
    frame["AgeGrpStart"] = pd.to_numeric(frame["AgeGrpStart"], errors="coerce")
    frame["band"] = np.select(
        [
            frame["AgeGrpStart"].between(25, 35),
            frame["AgeGrpStart"].between(40, 60),
            frame["AgeGrpStart"] >= 65,
        ],
        ["20-39", "40-64", "65+"],
        default=None,
    )
    frame = frame[frame["band"].notna()]
    frame["population"] = frame["PopMale"] + frame["PopFemale"]
    out = frame.groupby(["ISO3_code", "band"], as_index=False)["population"].sum()
    expected = pd.MultiIndex.from_product(
        [sorted(countries), ["20-39", "40-64", "65+"]], names=["ISO3_code", "band"]
    )
    missing = expected.difference(pd.MultiIndex.from_frame(out[["ISO3_code", "band"]]))
    if len(missing):
        raise ValueError(f"WPP calorie weights missing {len(missing)} cells")
    return out


def build_baseline_calories(
    *,
    source_path: Path = DEFAULT_SOURCE,
    manifest_path: Path = MANIFEST_PATH,
    wpp_path: Path = WPP_POPULATION_PATH,
) -> pd.DataFrame:
    manifest = read_manifest(manifest_path)
    usecols = [
        "type",
        "unit",
        "food_group",
        "region",
        "age",
        "sex",
        "residence",
        "year",
        "stats",
        "value",
    ]
    source = pd.read_csv(source_path, usecols=usecols)
    source = source[
        (source["type"] == "prim")
        & (source["unit"] == "kcal/d")
        & (source["food_group"] == "all-fg")
        & (source["sex"] == "BTH")
        & (source["residence"] == "all-u")
        & (source["year"] == REFERENCE_YEAR)
        & (source["stats"] == "mean")
        & source["age"].isin(["20-39", "40-64", "65+"])
    ]
    if source.duplicated(["region", "age"]).any():
        raise ValueError("GDD-IA calorie source has duplicate country-age rows")
    countries = set(manifest["calorie_source_country"])
    source = source[source["region"].isin(countries)].copy()
    missing = countries - set(source["region"])
    if missing:
        raise ValueError(f"GDD-IA calorie source missing countries: {sorted(missing)}")
    source["value"] = pd.to_numeric(source["value"], errors="coerce")
    if not np.isfinite(source["value"]).all() or (source["value"] < 0).any():
        raise ValueError("GDD-IA calorie values must be finite and non-negative")
    weights = _wpp_band_weights(countries, wpp_path)
    merged = source.merge(
        weights,
        left_on=["region", "age"],
        right_on=["ISO3_code", "band"],
        validate="one_to_one",
    )
    merged["weighted"] = merged["value"] * merged["population"]
    values = merged.groupby("region").agg(
        weighted=("weighted", "sum"), population=("population", "sum")
    )
    values["calories_kcal_per_day"] = values["weighted"] / values["population"]
    out = manifest[["country", "calorie_source_country"]].copy()
    out["calories_kcal_per_day"] = out["calorie_source_country"].map(
        values["calories_kcal_per_day"]
    )
    out["source_country"] = out["calorie_source_country"]
    out["source_year"] = REFERENCE_YEAR
    out = out[["country", "calories_kcal_per_day", "source_country", "source_year"]]
    if len(out) != len(manifest) or out.isna().any().any():
        raise ValueError("Calorie output is incomplete")
    return out.sort_values("country").reset_index(drop=True)


def write_baseline_calories(frame: pd.DataFrame, output: Path = OUT_PATH) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False, float_format="%.10g", lineterminator="\n")


def build_and_write_baseline_calories(
    *,
    source_path: Path = DEFAULT_SOURCE,
    manifest_path: Path = MANIFEST_PATH,
    output: Path = OUT_PATH,
) -> pd.DataFrame:
    """Build and write the country calorie baseline."""

    frame = build_baseline_calories(
        source_path=source_path, manifest_path=manifest_path
    )
    write_baseline_calories(frame, output)
    print(f"Wrote {len(frame)} rows to {output}")
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=OUT_PATH)
    args = parser.parse_args()
    build_and_write_baseline_calories(
        source_path=args.source,
        manifest_path=args.manifest,
        output=args.output,
    )


if __name__ == "__main__":
    main()
