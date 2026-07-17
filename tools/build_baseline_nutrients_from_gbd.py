#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build country nutrient baselines from GBD 2023 dietary-risk exposures.

The authenticated IHME inputs are development-only files under ``data/raw``.
This tool emits the small, adapted ``baseline_nutrients.csv`` bundled with the
package.  It is deliberately independent of GLADE and pins every source file by
name and SHA-256 digest.

Run from the repository root::

    python tools/build_baseline_nutrients_from_gbd.py
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
OUT_PATH = ROOT / "src" / "mealhealth" / "data" / "baseline_nutrients.csv"
BASELINE_INTAKE_PATH = ROOT / "src" / "mealhealth" / "data" / "baseline_intake.csv"
LOCATION_HIERARCHY_PATH = RAW_DIR / "IHME_GBD_2021_A1_HIERARCHIES_Y2024M05D15.XLSX"
LOCATION_HIERARCHY_URL = (
    "https://www.healthdata.org/sites/default/files/2024-05/"
    "IHME_GBD_2021_A1_HIERARCHIES_Y2024M05D15.XLSX"
)
WPP_POPULATION_PATH = RAW_DIR / "WPP_population.csv.gz"
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

# GBD adult ages used by dietary relative risks -> WPP age-group start.
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


@dataclass(frozen=True)
class NutrientSource:
    """Pinned GBD source metadata for one model nutrient."""

    nutrient: str
    relative_path: str
    sha256: str
    exposure_unit: str

    @property
    def path(self) -> Path:
        return RAW_DIR / self.relative_path


OMEGA3_SOURCE = NutrientSource(
    nutrient="omega3",
    relative_path=(
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_2/"
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_LOW_IN_SEAFOOD_OMEGA_3_"
        "FATTY_ACIDS_Y2025M10D10.CSV"
    ),
    sha256="4e80f1047b13251d674da636d6cce35cb56b64878e79774c59f927d569d9b28f",
    # This release's documented exposure definition is seafood EPA + DHA,
    # expressed in g/day. The raw CSV has no unit column, so the unit is bound
    # to this exact risk token and pinned file rather than inferred from values.
    exposure_unit="g/day",
)

# Keep the phase-2 sodium input pinned and discoverable, but do not build or
# register it until dietary intake -> 24 h urinary sodium has been designed.
SODIUM_SOURCE = NutrientSource(
    nutrient="sodium",
    relative_path=(
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_1/"
        "IHME_GBD_2023_RISK_EXPOSURE_DIET_HIGH_IN_SODIUM_Y2025M10D10.CSV"
    ),
    sha256="0ea88321aba71f3c4cba0ca02472928ff06c78600e3a0a182bae4588217d23fd",
    exposure_unit="g/day (24 h urinary sodium)",
)

# IHME names that pycountry cannot resolve reliably. Kept aligned with
# tools/prepare_data.py for the national-location subset used here.
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

NUTRIENT_COUNTRY_PROXIES = {"GUF": "FRA"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
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
    source: NutrientSource, *, verify_checksum: bool = True
) -> pd.DataFrame:
    path = source.path
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {source.nutrient} GBD exposure input:\n  {path}\n"
            "See docs/data_sources.md for authenticated download instructions."
        )
    if verify_checksum:
        actual = _sha256(path)
        if actual != source.sha256:
            raise ValueError(
                f"SHA-256 mismatch for {path.name}: expected {source.sha256}, "
                f"got {actual}. Update the pinned source intentionally."
            )

    df = pd.read_csv(path)
    if list(df.columns) != EXPOSURE_COLUMNS:
        raise ValueError(
            f"Unexpected schema for {path.name}: expected {EXPOSURE_COLUMNS}, "
            f"got {list(df.columns)}"
        )
    if set(df["measure_id"].unique()) != {19} or set(df["measure"].unique()) != {
        "continuous"
    }:
        raise ValueError("GBD nutrient exposure must be measure_id=19/continuous")
    if set(df["year_id"].unique()) != set(range(1990, 2024)):
        raise ValueError("GBD nutrient exposure must contain every year 1990-2023")
    sex_pairs = set(df[["sex_id", "sex"]].itertuples(index=False, name=None))
    if sex_pairs != {(1, "Male"), (2, "Female")}:
        raise ValueError(f"Unexpected GBD sex structure: {sorted(sex_pairs)}")
    missing_ages = set(ADULT_AGE_START) - set(df["age_group_id"].unique())
    if missing_ages:
        raise ValueError(f"GBD nutrient exposure missing adult ages: {missing_ages}")
    observed_age_names = set(
        df.loc[
            df["age_group_id"].isin(ADULT_AGE_START),
            ["age_group_id", "age_group_name"],
        ].itertuples(index=False, name=None)
    )
    expected_age_names = set(ADULT_AGE_NAME.items())
    if observed_age_names != expected_age_names:
        raise ValueError(
            "Unexpected GBD adult age names: "
            f"expected {sorted(expected_age_names)}, got {sorted(observed_age_names)}"
        )

    for col in ("mean", "lower", "upper"):
        values = pd.to_numeric(df[col], errors="coerce")
        if not np.isfinite(values).all():
            raise ValueError(f"Non-finite {col} values in {path.name}")
        df[col] = values
    if (df["mean"] < 0).any():
        raise ValueError(f"Negative mean exposure in {path.name}")
    if ((df["lower"] > df["mean"]) | (df["mean"] > df["upper"])).any():
        raise ValueError(f"Expected lower <= mean <= upper in {path.name}")
    return df


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
    national = national.dropna(subset=["source_country"])
    if national["source_country"].duplicated().any():
        raise ValueError("GBD hierarchy maps multiple national locations to one ISO3")
    return national[["location_id", "source_country"]]


def _wpp_age_sex_weights(wpp_path: Path, countries: set[str]) -> pd.DataFrame:
    usecols = [
        "ISO3_code",
        "Variant",
        "Time",
        "AgeGrpStart",
        "AgeGrpSpan",
        "PopMale",
        "PopFemale",
    ]
    wpp = pd.read_csv(wpp_path, usecols=usecols, low_memory=False)
    wpp = wpp[
        (wpp["Variant"].astype(str).str.lower() == "medium")
        & (pd.to_numeric(wpp["Time"], errors="coerce") == REFERENCE_YEAR)
        & (wpp["ISO3_code"].isin(countries))
    ].copy()
    wpp["AgeGrpStart"] = pd.to_numeric(wpp["AgeGrpStart"], errors="coerce")
    wpp["AgeGrpSpan"] = pd.to_numeric(wpp["AgeGrpSpan"], errors="coerce")

    start_to_gbd = {v: k for k, v in ADULT_AGE_START.items() if v < 95}
    wpp["age_group_id"] = wpp["AgeGrpStart"].map(start_to_gbd)
    wpp.loc[wpp["AgeGrpStart"] >= 95, "age_group_id"] = 235
    wpp = wpp[wpp["age_group_id"].notna()].copy()

    weights = wpp.melt(
        id_vars=["ISO3_code", "age_group_id"],
        value_vars=["PopMale", "PopFemale"],
        var_name="sex_column",
        value_name="population",
    )
    weights["sex_id"] = weights["sex_column"].map({"PopMale": 1, "PopFemale": 2})
    weights["population"] = pd.to_numeric(weights["population"], errors="coerce")
    weights["age_group_id"] = weights["age_group_id"].astype(int)
    weights = (
        weights.groupby(["ISO3_code", "age_group_id", "sex_id"], as_index=False)[
            "population"
        ]
        .sum()
        .rename(columns={"ISO3_code": "source_country"})
    )
    if (
        not np.isfinite(weights["population"]).all()
        or (weights["population"] < 0).any()
    ):
        raise ValueError("WPP population weights must be finite and non-negative")

    expected = pd.MultiIndex.from_product(
        [sorted(countries), sorted(ADULT_AGE_START), (1, 2)],
        names=["source_country", "age_group_id", "sex_id"],
    )
    actual = pd.MultiIndex.from_frame(
        weights[["source_country", "age_group_id", "sex_id"]]
    )
    missing = expected.difference(actual)
    if len(missing):
        raise ValueError(f"WPP population weights missing {len(missing)} cells")
    return weights


def build_baseline_nutrients(
    *,
    source: NutrientSource = OMEGA3_SOURCE,
    baseline_intake_path: Path = BASELINE_INTAKE_PATH,
    location_hierarchy_path: Path = LOCATION_HIERARCHY_PATH,
    wpp_path: Path = WPP_POPULATION_PATH,
    verify_checksum: bool = True,
) -> pd.DataFrame:
    """Return country-weighted adult exposure for one pinned nutrient source."""
    if source.nutrient != "omega3" or source.exposure_unit != "g/day":
        raise ValueError("Only the implemented g/day omega3 source can be built")

    target_countries = sorted(
        pd.read_csv(baseline_intake_path, usecols=["country"])["country"].unique()
    )
    _ensure_location_hierarchy(location_hierarchy_path)
    exposure = _read_and_validate_exposure(source, verify_checksum=verify_checksum)
    exposure = exposure[
        (exposure["year_id"] == REFERENCE_YEAR)
        & (exposure["age_group_id"].isin(ADULT_AGE_START))
    ].copy()
    exposure = exposure.merge(
        _national_locations(location_hierarchy_path), on="location_id", how="inner"
    )

    direct_needed = set(target_countries) - set(NUTRIENT_COUNTRY_PROXIES)
    present = set(exposure["source_country"])
    missing = direct_needed - present
    if missing:
        raise ValueError(
            f"GBD {source.nutrient} exposure missing target countries: "
            f"{sorted(missing)}"
        )
    exposure = exposure[exposure["source_country"].isin(direct_needed)].copy()
    key = ["source_country", "age_group_id", "sex_id"]
    if exposure.duplicated(key).any():
        raise ValueError("Duplicate GBD exposure age-sex cells after filtering")

    weights = _wpp_age_sex_weights(wpp_path, direct_needed)
    merged = exposure.merge(weights, on=key, how="left", validate="one_to_one")
    if merged["population"].isna().any():
        raise ValueError("Missing WPP population weight for a GBD exposure cell")
    merged["weighted_mean"] = merged["mean"] * merged["population"]
    agg = merged.groupby("source_country", as_index=False).agg(
        weighted_mean=("weighted_mean", "sum"), population=("population", "sum")
    )
    if (agg["population"] <= 0).any():
        raise ValueError("Adult population weight must be positive for every country")
    agg["intake_g_per_day"] = agg["weighted_mean"] / agg["population"]

    records = {
        row.source_country: float(row.intake_g_per_day)
        for row in agg.itertuples(index=False)
    }
    out_rows = []
    for country in target_countries:
        source_country = NUTRIENT_COUNTRY_PROXIES.get(country, country)
        if source_country not in records:
            raise ValueError(f"No {source.nutrient} baseline for {country}")
        out_rows.append(
            {
                "country": country,
                "nutrient": source.nutrient,
                "intake_g_per_day": records[source_country],
                "source_country": source_country,
                "source_year": REFERENCE_YEAR,
            }
        )
    out = pd.DataFrame(out_rows)
    if out.duplicated(["country", "nutrient"]).any():
        raise ValueError("Duplicate country/nutrient output rows")
    if (
        not np.isfinite(out["intake_g_per_day"]).all()
        or (out["intake_g_per_day"] < 0).any()
    ):
        raise ValueError("Nutrient baselines must be finite and non-negative")
    return out.sort_values(["country", "nutrient"]).reset_index(drop=True)


def write_baseline_nutrients(df: pd.DataFrame, output: Path = OUT_PATH) -> None:
    """Write a byte-stable bundled nutrient baseline."""
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False, float_format="%.10g", lineterminator="\n")


def main() -> None:
    # Verify both staged release files even though sodium remains inactive.
    _read_and_validate_exposure(SODIUM_SOURCE)
    out = build_baseline_nutrients()
    write_baseline_nutrients(out)
    print(f"Wrote {len(out)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
