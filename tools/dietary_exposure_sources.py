#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared source, proxy, and unit contracts for baseline diet builders.

This module is intentionally importable from the development-only ``tools``
directory.  Keeping the source registry here prevents the direct, calorie, and
mediator builders from silently acquiring different country sets or units.
"""

from __future__ import annotations

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
REFERENCE_YEAR = 2020
MANIFEST_PATH = ROOT / "tools" / "reference" / "baseline_country_sources.csv"
WPP_POPULATION_PATH = RAW_DIR / "WPP_population.csv.gz"
LOCATION_HIERARCHY_PATH = RAW_DIR / "IHME_GBD_2021_A1_HIERARCHIES_Y2024M05D15.XLSX"
LOCATION_HIERARCHY_URL = (
    "https://www.healthdata.org/sites/default/files/2024-05/"
    "IHME_GBD_2021_A1_HIERARCHIES_Y2024M05D15.XLSX"
)

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

# Native GBD exposure axes are g/day for all direct dietary factors.  The
# processed-meat release is already an as-eaten product basis; unlike the
# legumes axis it must not be multiplied by a cooked/raw conversion.
BASIS_FACTORS = {
    "fruits": 1.0,
    "vegetables": 1.0,
    "whole_grains": 1.0,
    "legumes": 0.40,
    "nuts_seeds": 1.0,
    "red_meat": 1.43,
    "processed_meat": 1.0,
    "omega3": 1.0,
}


@dataclass(frozen=True)
class ExposureSource:
    """Pinned GBD continuous-exposure source."""

    name: str
    relative_path: str
    sha256: str
    unit: str

    def path(self, raw_dir: Path = RAW_DIR) -> Path:
        return raw_dir / self.relative_path


DIRECT_SOURCES = {
    "fruits": ExposureSource(
        "fruits",
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_1/"
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_LOW_IN_FRUITS_Y2025M10D10.CSV",
        "1bb089898d83ead3d5bd2843663bae3253fa31566aaf020cfdaab1333d99459a",
        "g/day",
    ),
    "vegetables": ExposureSource(
        "vegetables",
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_2/"
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_LOW_IN_VEGETABLES_Y2025M10D10.CSV",
        "eb77c6d4bf4528d628116b8ca97faa0ff27483243885e27cfc3715e2fac2d562",
        "g/day",
    ),
    "whole_grains": ExposureSource(
        "whole_grains",
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_2/"
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_LOW_IN_WHOLE_GRAINS_Y2025M10D10.CSV",
        "ec0dd001d4fd7d808209fe1a2baa4a1e11211b51f4d0b55985440f4353dfb0c9",
        "g/day",
    ),
    "legumes": ExposureSource(
        "legumes",
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_2/"
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_LOW_IN_LEGUMES_Y2025M10D10.CSV",
        "c968ee4d61b12500d0670e75d5e3d31b40666c74e56414bd25ff9688d5307fbb",
        "g/day",
    ),
    "nuts_seeds": ExposureSource(
        "nuts_seeds",
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_2/"
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_LOW_IN_NUTS_AND_SEEDS_Y2025M10D10.CSV",
        "a426371525fcfbbc5c356ab59b1c7f42a4d7cb270fd7278e195b6809f60e1de7",
        "g/day",
    ),
    "red_meat": ExposureSource(
        "red_meat",
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_1/"
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_HIGH_IN_RED_MEAT_Y2025M10D10.CSV",
        "e49458b2e4671b1ecd9633d27bd3712527f3e1c5d9a3babde57f101c17f5f871",
        "g/day",
    ),
    "processed_meat": ExposureSource(
        "processed_meat",
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_1/"
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_HIGH_IN_PROCESSED_MEAT_Y2025M10D10.CSV",
        "c26f184c93d79395e7be0853013836c7d1e0949dab0d0b8f38209c6b2190845a",
        "g/day",
    ),
    "omega3": ExposureSource(
        "omega3",
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_2/"
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_LOW_IN_SEAFOOD_OMEGA_3_FATTY_ACIDS_"
        "Y2025M10D10.CSV",
        "4e80f1047b13251d674da636d6cce35cb56b64878e79774c59f927d569d9b28f",
        "g/day",
    ),
}

MEDIATOR_SOURCES = {
    "sodium_urinary": ExposureSource(
        name="sodium_urinary",
        relative_path=(
            "IHME_GBD_2023_RISK_EXPOSURE_DIET_1/"
            "IHME_GBD_2023_RISK_EXPOSURE_DIET_HIGH_IN_SODIUM_Y2025M10D10.CSV"
        ),
        sha256=("0ea88321aba71f3c4cba0ca02472928ff06c78600e3a0a182bae4588217d23fd"),
        unit="g/day (24 h urinary sodium)",
    ),
    "sbp": ExposureSource(
        name="sbp",
        relative_path=(
            "IHME_GBD_2023_RISK_EXPOSURE_OTHER_1/"
            "IHME_GBD_2023_RISK_EXPOSURE_HIGH_SYSTOLIC_BLOOD_PRESSURE_"
            "Y2025M10D10.CSV"
        ),
        sha256=("dd317224c33981577ae910f0dd97b6f205de7067b21fee29cefd6736aecaf27e"),
        unit="mm Hg",
    ),
}

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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(
    path: Path = MANIFEST_PATH, *, expected_country_count: int | None = 175
) -> pd.DataFrame:
    """Read and validate the shared baseline country/source manifest."""

    frame = pd.read_csv(path, dtype=str)
    expected = ["country", "gbd_exposure_source_country", "calorie_source_country"]
    if list(frame.columns) != expected:
        raise ValueError(
            f"Invalid baseline source manifest columns: {frame.columns.tolist()}"
        )
    if (
        frame[expected].isna().any().any()
        or frame[expected].duplicated("country").any()
    ):
        raise ValueError("Baseline source manifest has missing or duplicate countries")
    if expected_country_count is not None and len(frame) != expected_country_count:
        raise ValueError(
            f"Baseline source manifest must contain {expected_country_count} countries"
        )
    valid_codes = frame[expected].apply(
        lambda column: column.str.fullmatch(r"[A-Z]{3}").all()
    )
    if frame.empty or not valid_codes.all():
        raise ValueError("Baseline source manifest country/source codes must be ISO-3")
    return frame.sort_values("country").reset_index(drop=True)


def map_country(name: str) -> str | None:
    if name in COUNTRY_NAME_OVERRIDES:
        return COUNTRY_NAME_OVERRIDES[name]
    try:
        matches = pycountry.countries.search_fuzzy(name)
    except LookupError:
        return None
    return matches[0].alpha_3 if matches else None


def read_exposure(
    source: ExposureSource,
    *,
    raw_dir: Path = RAW_DIR,
    verify_checksum: bool = True,
) -> pd.DataFrame:
    """Read and validate one complete GBD 2023 continuous-exposure file."""

    path = source.path(raw_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing GBD {source.name} exposure input:\n  {path}\n"
            "See docs/development/data_build.md for authenticated download instructions."
        )
    if verify_checksum:
        actual = sha256(path)
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
        raise ValueError("GBD exposure must be measure_id=19/continuous")
    if set(frame["year_id"].unique()) != set(range(1990, 2024)):
        raise ValueError("GBD exposure must contain every year 1990-2023")
    if set(frame[["sex_id", "sex"]].itertuples(index=False, name=None)) != {
        (1, "Male"),
        (2, "Female"),
    }:
        raise ValueError("Unexpected GBD sex structure")
    missing_ages = set(ADULT_AGE_START) - set(frame["age_group_id"].unique())
    if missing_ages:
        raise ValueError(f"GBD exposure is missing adult ages: {sorted(missing_ages)}")
    observed_age_names = set(
        frame.loc[
            frame["age_group_id"].isin(ADULT_AGE_START),
            ["age_group_id", "age_group_name"],
        ].itertuples(index=False, name=None)
    )
    if observed_age_names != set(ADULT_AGE_NAME.items()):
        raise ValueError(f"Unexpected GBD adult age names in {path.name}")
    for column in ("mean", "lower", "upper"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if (
        not np.isfinite(frame[["mean", "lower", "upper"]]).all().all()
        or (frame[["mean", "lower", "upper"]] < 0).any().any()
    ):
        raise ValueError("GBD exposure bounds must be finite and non-negative")
    if ((frame["lower"] > frame["mean"]) | (frame["mean"] > frame["upper"])).any():
        raise ValueError("Expected lower <= mean <= upper")
    return frame


def ensure_location_hierarchy(
    path: Path = LOCATION_HIERARCHY_PATH, *, mortality_path: Path | None = None
) -> None:
    """Download the public hierarchy unless a local national-location fallback exists."""

    mortality_path = mortality_path or (
        path.parent / "IHME-GBD_2023-death-rates-2020.csv"
    )
    if path.exists() or mortality_path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        LOCATION_HIERARCHY_URL, headers={"User-Agent": "Mozilla/5.0"}
    )
    with (
        urllib.request.urlopen(request, timeout=120) as response,
        path.open("wb") as output,
    ):  # noqa: S310
        shutil.copyfileobj(response, output)


def national_locations(
    path: Path = LOCATION_HIERARCHY_PATH, *, mortality_path: Path | None = None
) -> pd.DataFrame:
    """Return a unique GBD national-location to ISO-3 mapping."""

    mortality_path = mortality_path or (
        path.parent / "IHME-GBD_2023-death-rates-2020.csv"
    )
    if not path.exists():
        if not mortality_path.exists():
            raise FileNotFoundError(f"Missing GBD location hierarchy: {path}")
        frame = pd.read_csv(
            mortality_path, usecols=["location_id", "location_name"]
        ).drop_duplicates()
        frame["source_country"] = frame["location_name"].map(map_country)
        frame = frame.dropna(subset=["source_country"])
        if (
            frame["location_id"].duplicated().any()
            or frame["source_country"].duplicated().any()
        ):
            raise ValueError("GBD mortality locations must map uniquely to ISO-3")
        return frame[["location_id", "source_country"]]
    hierarchy = pd.read_excel(path, sheet_name="GBD 2021 Locations Hierarchy")
    required = {"Location ID", "Location Name", "Level"}
    if not required <= set(hierarchy.columns):
        raise ValueError("GBD location hierarchy is missing required columns")
    national = hierarchy.loc[
        hierarchy["Level"] == 3, ["Location ID", "Location Name"]
    ].drop_duplicates()
    national = national.rename(
        columns={"Location ID": "location_id", "Location Name": "location_name"}
    )
    national["source_country"] = national["location_name"].map(map_country)
    national = national.dropna(subset=["source_country"])
    if (
        national["location_id"].duplicated().any()
        or national["source_country"].duplicated().any()
    ):
        raise ValueError(
            "GBD hierarchy must map each national location and ISO-3 uniquely"
        )
    return national[["location_id", "source_country"]]


def select_exposure_cells(
    frame: pd.DataFrame,
    *,
    label: str,
    locations: pd.DataFrame,
    source_countries: set[str],
) -> pd.DataFrame:
    """Select one complete 2020 adult age-sex grid for the requested countries."""

    selected = frame[
        (frame["year_id"] == REFERENCE_YEAR)
        & frame["age_group_id"].isin(ADULT_AGE_START)
    ].merge(locations, on="location_id", how="inner", validate="many_to_one")
    selected = selected[selected["source_country"].isin(source_countries)].copy()
    key = ["source_country", "age_group_id", "sex_id"]
    if selected.duplicated(key).any():
        raise ValueError(f"Duplicate {label} age-sex cells after filtering")
    expected = pd.MultiIndex.from_product(
        [sorted(source_countries), sorted(ADULT_AGE_START), (1, 2)], names=key
    )
    actual = pd.MultiIndex.from_frame(selected[key])
    missing = expected.difference(actual)
    if len(missing):
        raise ValueError(f"GBD {label} exposure missing {len(missing)} target cells")
    return selected[key + ["mean", "lower", "upper"]]


def wpp_age_sex_weights(
    countries: set[str], path: Path = WPP_POPULATION_PATH
) -> pd.DataFrame:
    columns = ["ISO3_code", "Variant", "Time", "AgeGrpStart", "PopMale", "PopFemale"]
    frame = pd.read_csv(path, usecols=columns, low_memory=False)
    frame = frame[
        (frame["Variant"].astype(str).str.lower() == "medium")
        & (frame["Time"] == REFERENCE_YEAR)
        & frame["ISO3_code"].isin(countries)
    ].copy()
    frame["AgeGrpStart"] = pd.to_numeric(frame["AgeGrpStart"], errors="coerce")
    mapping = {start: age_id for age_id, start in ADULT_AGE_START.items() if start < 95}
    frame["age_group_id"] = frame["AgeGrpStart"].map(mapping)
    frame.loc[frame["AgeGrpStart"] >= 95, "age_group_id"] = 235
    frame = frame[frame["age_group_id"].notna()]
    melted = frame.melt(
        id_vars=["ISO3_code", "age_group_id"],
        value_vars=["PopMale", "PopFemale"],
        var_name="sex_column",
        value_name="population",
    )
    melted["sex_id"] = melted["sex_column"].map({"PopMale": 1, "PopFemale": 2})
    melted["population"] = pd.to_numeric(melted["population"], errors="coerce")
    out = (
        melted.groupby(["ISO3_code", "age_group_id", "sex_id"], as_index=False)[
            ["population"]
        ]
        .sum()
        .rename(columns={"ISO3_code": "source_country"})
    )
    expected = pd.MultiIndex.from_product(
        [sorted(countries), sorted(ADULT_AGE_START), (1, 2)],
        names=["source_country", "age_group_id", "sex_id"],
    )
    missing = expected.difference(
        pd.MultiIndex.from_frame(out[["source_country", "age_group_id", "sex_id"]])
    )
    if len(missing):
        raise ValueError(f"WPP population weights missing {len(missing)} cells")
    return out
