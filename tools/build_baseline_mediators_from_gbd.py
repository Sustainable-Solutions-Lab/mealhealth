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

    python tools/build_baseline_mediators_from_gbd.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
import urllib.request

import numpy as np
import pandas as pd
import pycountry

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "src" / "mealhealth" / "data" / "baseline_mediators.csv"
BASELINE_INTAKE_PATH = ROOT / "src" / "mealhealth" / "data" / "baseline_intake.csv"
LOCATION_HIERARCHY_PATH = RAW_DIR / "IHME_GBD_2021_A1_HIERARCHIES_Y2024M05D15.XLSX"
LOCATION_HIERARCHY_URL = (
    "https://www.healthdata.org/sites/default/files/2024-05/"
    "IHME_GBD_2021_A1_HIERARCHIES_Y2024M05D15.XLSX"
)
REFERENCE_YEAR = 2020

EXPOSURE_COLUMNS = [
    "age_group_id",
    "age_group_name",
    "sex_id",
    "sex",
    "year_id",
    "location_id",
    "location_name",
    "measure_id",
    "measure",
    "mean",
    "lower",
    "upper",
]

ADULT_AGE_START = {
    10: 25,
    11: 30,
    12: 35,
    13: 40,
    14: 45,
    15: 50,
    16: 55,
    17: 60,
    18: 65,
    19: 70,
    20: 75,
    30: 80,
    31: 85,
    32: 90,
    235: 95,
}
ADULT_AGE_NAME = {
    age_id: ("95 plus" if start == 95 else f"{start} to {start + 4}")
    for age_id, start in ADULT_AGE_START.items()
}
MODEL_AGE = {
    age_id: ("95+" if start == 95 else f"{start}-{start + 4}")
    for age_id, start in ADULT_AGE_START.items()
}


@dataclass(frozen=True)
class ExposureSource:
    """Pinned GBD continuous-exposure source."""

    name: str
    relative_path: str
    sha256: str
    unit: str

    def path(self, raw_dir: Path) -> Path:
        return raw_dir / self.relative_path


SODIUM_SOURCE = ExposureSource(
    name="sodium_urinary",
    relative_path=(
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_1/"
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_HIGH_IN_SODIUM_Y2025M10D10.CSV"
    ),
    sha256="0ea88321aba71f3c4cba0ca02472928ff06c78600e3a0a182bae4588217d23fd",
    unit="g/day (24 h urinary sodium)",
)
SBP_SOURCE = ExposureSource(
    name="sbp",
    relative_path=(
        "IHME_GBD_2023_RISK_EXPOSURE_OTHER_1/"
        "IHME_GBD_2023_RISK_EXPOSURE_HIGH_SYSTOLIC_BLOOD_PRESSURE_"
        "Y2025M10D10.CSV"
    ),
    sha256="dd317224c33981577ae910f0dd97b6f205de7067b21fee29cefd6736aecaf27e",
    unit="mm Hg",
)

COUNTRY_NAME_OVERRIDES = {
    "Bolivia (Plurinational State of)": "BOL",
    "Bonaire, Saint Eustatius and Saba": "BES",
    "Cabo Verde": "CPV",
    "Côte d'Ivoire": "CIV",
    "Democratic People's Republic of Korea": "PRK",
    "Democratic Republic of the Congo": "COD",
    "French Guiana": "GUF",
    "Iran (Islamic Republic of)": "IRN",
    "Lao People's Democratic Republic": "LAO",
    "Micronesia (Federated States of)": "FSM",
    "Niger": "NER",
    "Republic of Korea": "KOR",
    "Republic of Moldova": "MDA",
    "Republic of the Congo": "COG",
    "Saint Barthélemy": "BLM",
    "Saint Martin (French part)": "MAF",
    "Sint Maarten (Dutch part)": "SXM",
    "Taiwan (Province of China)": "TWN",
    "The former Yugoslav Republic of Macedonia": "MKD",
    "Türkiye": "TUR",
    "United Kingdom of Great Britain and Northern Ireland": "GBR",
    "United Republic of Tanzania": "TZA",
    "United States of America": "USA",
    "United States Virgin Islands": "VIR",
    "Venezuela (Bolivarian Republic of)": "VEN",
    "Viet Nam": "VNM",
}

# Keep mediator proxies aligned with the currently bundled nutrient baseline.
MEDIATOR_COUNTRY_PROXIES = {"GUF": "FRA"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _map_country_to_iso3(name: str) -> str | None:
    if name in COUNTRY_NAME_OVERRIDES:
        return COUNTRY_NAME_OVERRIDES[name]
    try:
        matches = pycountry.countries.search_fuzzy(name)
    except LookupError:
        return None
    return matches[0].alpha_3 if matches else None


def _read_and_validate_exposure(
    source: ExposureSource,
    *,
    raw_dir: Path = RAW_DIR,
    verify_checksum: bool = True,
) -> pd.DataFrame:
    path = source.path(raw_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing GBD {source.name} exposure input:\n  {path}\n"
            "See docs/data_sources.md for authenticated download instructions."
        )
    if verify_checksum:
        actual = _sha256(path)
        if actual != source.sha256:
            raise ValueError(
                f"SHA-256 mismatch for {path.name}: expected {source.sha256}, "
                f"got {actual}. Update the pinned source intentionally."
            )

    frame = pd.read_csv(path)
    if list(frame.columns) != EXPOSURE_COLUMNS:
        raise ValueError(
            f"Unexpected schema for {path.name}: expected {EXPOSURE_COLUMNS}, "
            f"got {list(frame.columns)}"
        )
    if set(frame["measure_id"].unique()) != {19} or set(frame["measure"].unique()) != {
        "continuous"
    }:
        raise ValueError("GBD mediator exposure must be measure_id=19/continuous")
    if set(frame["year_id"].unique()) != set(range(1990, 2024)):
        raise ValueError("GBD mediator exposure must contain every year 1990-2023")
    sex_pairs = set(frame[["sex_id", "sex"]].itertuples(index=False, name=None))
    if sex_pairs != {(1, "Male"), (2, "Female")}:
        raise ValueError(f"Unexpected GBD sex structure: {sorted(sex_pairs)}")
    missing_ages = set(ADULT_AGE_START) - set(frame["age_group_id"].unique())
    if missing_ages:
        raise ValueError(f"GBD mediator exposure missing adult ages: {missing_ages}")
    observed_age_names = set(
        frame.loc[
            frame["age_group_id"].isin(ADULT_AGE_START),
            ["age_group_id", "age_group_name"],
        ].itertuples(index=False, name=None)
    )
    if observed_age_names != set(ADULT_AGE_NAME.items()):
        raise ValueError(f"Unexpected GBD adult age names in {path.name}")

    for column in ("mean", "lower", "upper"):
        values = pd.to_numeric(frame[column], errors="coerce")
        if not np.isfinite(values).all():
            raise ValueError(f"Non-finite {column} values in {path.name}")
        frame[column] = values
    if (frame[["mean", "lower", "upper"]] < 0).any(axis=None):
        raise ValueError(f"Negative exposure in {path.name}")
    if ((frame["lower"] > frame["mean"]) | (frame["mean"] > frame["upper"])).any():
        raise ValueError(f"Expected lower <= mean <= upper in {path.name}")
    return frame


def _ensure_location_hierarchy(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(  # noqa: S310 (trusted IHME host)
        LOCATION_HIERARCHY_URL, headers={"User-Agent": "Mozilla/5.0"}
    )
    with (
        urllib.request.urlopen(request, timeout=120) as response,
        path.open(  # noqa: S310
            "wb"
        ) as output,
    ):
        shutil.copyfileobj(response, output)


def _national_locations(hierarchy_path: Path) -> pd.DataFrame:
    hierarchy = pd.read_excel(hierarchy_path, sheet_name="GBD 2021 Locations Hierarchy")
    required = {"Location ID", "Location Name", "Level"}
    missing_columns = required - set(hierarchy.columns)
    if missing_columns:
        raise ValueError(
            f"GBD location hierarchy missing columns: {sorted(missing_columns)}"
        )
    national = hierarchy.loc[
        hierarchy["Level"] == 3, ["Location ID", "Location Name"]
    ].drop_duplicates()
    national = national.rename(
        columns={"Location ID": "location_id", "Location Name": "location_name"}
    )
    if national["location_id"].duplicated().any():
        raise ValueError("GBD hierarchy maps a national location_id to >1 name")
    national["source_country"] = national["location_name"].map(_map_country_to_iso3)
    if national["source_country"].isna().any():
        names = sorted(national.loc[national["source_country"].isna(), "location_name"])
        raise ValueError(f"Could not map national GBD locations: {names}")
    if national["source_country"].duplicated().any():
        raise ValueError("GBD hierarchy maps multiple national locations to one ISO3")
    return national[["location_id", "source_country"]]


def _select_source_cells(
    frame: pd.DataFrame,
    *,
    prefix: str,
    locations: pd.DataFrame,
    source_countries: set[str],
) -> pd.DataFrame:
    frame = frame[
        (frame["year_id"] == REFERENCE_YEAR)
        & (frame["age_group_id"].isin(ADULT_AGE_START))
    ].merge(locations, on="location_id", how="inner", validate="many_to_one")
    frame = frame[frame["source_country"].isin(source_countries)].copy()
    key = ["source_country", "age_group_id", "sex_id"]
    if frame.duplicated(key).any():
        raise ValueError(f"Duplicate {prefix} age-sex cells after filtering")
    missing = source_countries - set(frame["source_country"])
    if missing:
        raise ValueError(
            f"GBD {prefix} exposure missing target countries: {sorted(missing)}"
        )
    return frame[key + ["mean", "lower", "upper"]].rename(
        columns={
            "mean": f"{prefix}_mean",
            "lower": f"{prefix}_lower",
            "upper": f"{prefix}_upper",
        }
    )


def build_baseline_mediators(
    *,
    raw_dir: Path = RAW_DIR,
    baseline_intake_path: Path = BASELINE_INTAKE_PATH,
    location_hierarchy_path: Path | None = None,
    sodium_source: ExposureSource = SODIUM_SOURCE,
    sbp_source: ExposureSource = SBP_SOURCE,
    verify_checksum: bool = True,
) -> pd.DataFrame:
    """Return exact 2020 country-age-sex sodium and SBP mean exposures."""

    location_hierarchy_path = location_hierarchy_path or (
        raw_dir / LOCATION_HIERARCHY_PATH.name
    )
    _ensure_location_hierarchy(location_hierarchy_path)
    target_countries = sorted(
        pd.read_csv(baseline_intake_path, usecols=["country"])["country"].unique()
    )
    source_countries = {
        MEDIATOR_COUNTRY_PROXIES.get(country, country) for country in target_countries
    }
    locations = _national_locations(location_hierarchy_path)
    sodium = _select_source_cells(
        _read_and_validate_exposure(
            sodium_source, raw_dir=raw_dir, verify_checksum=verify_checksum
        ),
        prefix="sodium_urinary_g_per_day",
        locations=locations,
        source_countries=source_countries,
    )
    sbp = _select_source_cells(
        _read_and_validate_exposure(
            sbp_source, raw_dir=raw_dir, verify_checksum=verify_checksum
        ),
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
    for country in target_countries:
        source_country = MEDIATOR_COUNTRY_PROXIES.get(country, country)
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output", type=Path, default=OUT_PATH)
    parser.add_argument("--no-checksum", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    frame = build_baseline_mediators(
        raw_dir=args.raw_dir, verify_checksum=not args.no_checksum
    )
    write_baseline_mediators(frame, args.output)
    print(f"Wrote {len(frame)} rows to {args.output}")


if __name__ == "__main__":
    main()
