#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build the bundled health & demographic data for ``mealhealth`` from raw sources.

This is a *one-time* developer tool, not part of the installed package. It
regenerates the small processed CSVs that ``mealhealth`` ships under
``src/mealhealth/data/`` directly from the documented raw datasets — the package
no longer depends on any other project to prepare its data.

Outputs (schemas documented in ``src/mealhealth/data/DATA_PROVENANCE.md``):

- ``relative_risks.csv``  GBD 2019 dietary dose–response curves (model basis):
                          risk_factor, cause, age, exposure_g_per_day,
                          rr_mean, rr_low, rr_high
- ``mortality.csv``       GBD 2023 cause-specific death rates:
                          age, cause, country, death_rate_per_1000
- ``population.csv``      UN WPP population by age: age, country, population
- ``life_table.csv``      UN WPP abridged life table: country, age, lx, ex

Raw inputs live under ``data/raw/`` (see ``docs/data_sources.md`` for how to
obtain each one). The two UN WPP files are public and downloaded automatically;
the two IHME GBD files require a (free) IHME account and must be downloaded
manually beforehand.

The *baseline diet* (``baseline_intake.csv``, ``baseline_calories.csv``) is a
separate dataset and is **not** built here — see
``tools/baseline_diet_from_foodopt.py`` and ``docs/data_sources.md``.

Run from the repository root with the dev environment::

    python tools/prepare_data.py
"""

from __future__ import annotations

import math
from pathlib import Path
import re
import urllib.request

import pandas as pd
import pycountry

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
REFERENCE_DIR = Path(__file__).resolve().parent / "reference"
OUT_DIR = ROOT / "src" / "mealhealth" / "data"

REFERENCE_YEAR = 2020

# Raw inputs (placed under data/raw/; see docs/data_sources.md).
GBD_RR_XLSX = RAW_DIR / "IHME_GBD_2019_RELATIVE_RISKS_Y2020M10D15.XLSX"
GBD_MORTALITY_CSV = RAW_DIR / f"IHME-GBD_2023-death-rates-{REFERENCE_YEAR}.csv"
WPP_POPULATION_GZ = RAW_DIR / "WPP_population.csv.gz"
WPP_LIFE_TABLE_GZ = RAW_DIR / "WPP_life_table.csv.gz"

# Bundled curated red-meat dose–response curve (literature meta-analyses).
RED_MEAT_RR_CSV = REFERENCE_DIR / "red_meat_rr_log_linear.csv"

# Public UN WPP downloads (CC BY 3.0 IGO), fetched automatically when absent.
WPP_POPULATION_URL = (
    "https://population.un.org/wpp/assets/Excel%20Files/"
    "1_Indicator%20(Standard)/CSV_FILES/"
    "WPP2024_Population1JanuaryByAge5GroupSex_Medium.csv.gz"
)
WPP_LIFE_TABLE_URL = (
    "https://population.un.org/wpp/assets/Excel%20Files/"
    "1_Indicator%20(Standard)/CSV_FILES/"
    "WPP2024_Life_Table_Abridged_Medium_2024-2100.csv.gz"
)

# Conversion of the RR-curve x-axis (and meat exposures) from GBD/GDD
# "as-consumed" bases onto the model's fresh/dry consumption basis, so that a
# consumption value can be looked up directly. Only legumes (cooked->dry) and
# the meats (cooked->fresh) differ from 1.0; fruits & vegetables are
# fresh->fresh and whole grains & nuts/seeds dry->dry. Values follow the
# standard cooked-weight conversion factors (cooked rice/pasta/beans ~0.4 dry;
# raw retail meat ~1.43x its cooked weight).
MEAT_COOKED_TO_FRESH = 1.43
LEGUMES_COOKED_TO_DRY = 0.40

RR_BASIS_FACTOR: dict[str, float] = {
    "legumes": LEGUMES_COOKED_TO_DRY,
    "red_meat": MEAT_COOKED_TO_FRESH,
    "processed_meat": MEAT_COOKED_TO_FRESH,
}

# IHME GBD relative-risk block names (XLSX column 0) -> model risk factor.
GBD_RISK_NAMES = {
    "Diet low in fruits": "fruits",
    "Diet low in vegetables": "vegetables",
    "Diet low in whole grains": "whole_grains",
    "Diet low in legumes": "legumes",
    "Diet low in nuts and seeds": "nuts_seeds",
    "Diet high in red meat": "red_meat",
    "Diet high in processed meat": "processed_meat",
}

# 15 adult GBD age groups; Excel column index -> label.
ADULT_AGE_COLUMNS = {
    13: "25-29",
    14: "30-34",
    15: "35-39",
    16: "40-44",
    17: "45-49",
    18: "50-54",
    19: "55-59",
    20: "60-64",
    21: "65-69",
    22: "70-74",
    23: "75-79",
    24: "80-84",
    25: "85-89",
    26: "90-94",
    27: "95+",
}
ADULT_AGE_LABELS = list(ADULT_AGE_COLUMNS.values())

AGE_BUCKETS = [
    "<1",
    "1-4",
    "5-9",
    "10-14",
    "15-19",
    "20-24",
    "25-29",
    "30-34",
    "35-39",
    "40-44",
    "45-49",
    "50-54",
    "55-59",
    "60-64",
    "65-69",
    "70-74",
    "75-79",
    "80-84",
    "85-89",
    "90-94",
    "95+",
]

# IHME outcome name -> model cause (GBD relative-risk sheet uses "type 2").
GBD_RR_CAUSE_MAP = {
    "Ischemic heart disease": "CHD",
    "Ischemic stroke": "Stroke",
    "Diabetes mellitus type 2": "T2DM",
    "Colon and rectum cancer": "CRC",
}

_NUM = re.compile(r"[-+]?(?:\d+\.\d+|\d+)")


def _ensure_raw_downloads() -> None:
    """Download the public UN WPP files into data/raw/ when missing.

    The two IHME GBD files require an account and cannot be auto-downloaded;
    a clear error points the developer at the acquisition guide.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for path, url in (
        (WPP_POPULATION_GZ, WPP_POPULATION_URL),
        (WPP_LIFE_TABLE_GZ, WPP_LIFE_TABLE_URL),
    ):
        if path.exists():
            continue
        print(f"Downloading {path.name} from UN WPP ...")
        urllib.request.urlretrieve(url, path)  # noqa: S310 (trusted UN URL)

    missing = [p for p in (GBD_RR_XLSX, GBD_MORTALITY_CSV) if not p.exists()]
    if missing:
        names = "\n  ".join(str(p) for p in missing)
        raise FileNotFoundError(
            "Missing IHME GBD raw inputs (require a free IHME account; see "
            f"docs/data_sources.md for how to download them):\n  {names}"
        )


# --------------------------------------------------------------------------
# Relative risks
# --------------------------------------------------------------------------


def _parse_rr_cell(cell: object) -> tuple[float, float, float] | None:
    """Parse '1.13 \\n (1 to 1.26)' -> (mean, low, high)."""
    if isinstance(cell, (int, float)) and not (
        isinstance(cell, float) and math.isnan(cell)
    ):
        v = float(cell)
        return v, v, v
    if not isinstance(cell, str):
        return None
    nums = [float(x) for x in _NUM.findall(cell)]
    if not nums:
        return None
    mean = nums[0]
    low = nums[1] if len(nums) > 1 else mean
    high = nums[2] if len(nums) > 2 else mean
    return mean, low, high


def _fill_missing_ages(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure every (risk, cause, exposure) triple has all 15 adult ages.

    Missing ages copy from the nearest younger age (then nearest older).
    """
    rows = []
    for (risk, cause, exp), grp in df.groupby(
        ["risk_factor", "cause", "exposure_g_per_day"]
    ):
        have = {r["age"]: r for _, r in grp.iterrows()}
        for i, age in enumerate(ADULT_AGE_LABELS):
            if age in have:
                continue
            donor = None
            for j in range(i - 1, -1, -1):
                if ADULT_AGE_LABELS[j] in have:
                    donor = have[ADULT_AGE_LABELS[j]]
                    break
            if donor is None:
                for j in range(i + 1, len(ADULT_AGE_LABELS)):
                    if ADULT_AGE_LABELS[j] in have:
                        donor = have[ADULT_AGE_LABELS[j]]
                        break
            assert donor is not None, (risk, cause, exp)
            rows.append(
                {
                    "risk_factor": risk,
                    "cause": cause,
                    "age": age,
                    "exposure_g_per_day": exp,
                    "rr_mean": donor["rr_mean"],
                    "rr_low": donor["rr_low"],
                    "rr_high": donor["rr_high"],
                }
            )
    if rows:
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    return df


def _parse_rr_block(
    raw: pd.DataFrame, start: int, end: int, risk: str, basis_factor: float
) -> list[dict]:
    """Parse one 'Diet ...' GBD RR block into tidy records.

    Exposures (``g/day``) are multiplied by *basis_factor* to convert the
    curve x-axis from the GBD basis onto the model's consumption basis.
    """
    records: list[dict] = []
    for _, row in raw.iloc[start:end].iterrows():
        outcome = row[0]
        exposure = row[1]
        if not isinstance(outcome, str) or not isinstance(exposure, str):
            continue
        if outcome not in GBD_RR_CAUSE_MAP:
            continue
        cause = GBD_RR_CAUSE_MAP[outcome]
        m = re.match(r"\s*([0-9.]+)\s*g/day", exposure)
        if not m:
            continue
        exp_g = float(m.group(1)) * basis_factor
        for col, age in ADULT_AGE_COLUMNS.items():
            if col >= len(row):
                continue
            parsed = _parse_rr_cell(row[col])
            if parsed is None:
                continue
            mean, low, high = parsed
            records.append(
                {
                    "risk_factor": risk,
                    "cause": cause,
                    "age": age,
                    "exposure_g_per_day": exp_g,
                    "rr_mean": mean,
                    "rr_low": low,
                    "rr_high": high,
                }
            )
    return records


def _parse_per_unit(per_unit: str) -> float:
    """Parse a per-unit string like '100 g/day' into the numeric g/day value."""
    parts = str(per_unit).strip().split()
    if len(parts) < 2:
        raise ValueError(f"Cannot parse per_unit: '{per_unit}'")
    return float(parts[0])


def _extract_age_attenuation(
    df: pd.DataFrame, risk_factor: str
) -> dict[tuple[str, str], float]:
    """Per-(cause, age) attenuation = log(RR_age)/log(RR_youngest) in [0, 1].

    Captures how the GBD dose–response effect attenuates with age, so the
    log-linear replacement curve keeps the original age structure.
    """
    risk_data = df[df["risk_factor"] == risk_factor]
    youngest = ADULT_AGE_LABELS[0]
    attenuation: dict[tuple[str, str], float] = {}

    for cause in risk_data["cause"].unique():
        cause_data = risk_data[risk_data["cause"] == cause]
        exposures = [
            x for x in sorted(cause_data["exposure_g_per_day"].unique()) if x > 0
        ]
        if not exposures:
            for age in ADULT_AGE_LABELS:
                attenuation[(cause, age)] = 1.0
            continue
        ref_x = exposures[-1]

        youngest_row = cause_data[
            (cause_data["age"] == youngest)
            & (cause_data["exposure_g_per_day"] == ref_x)
        ]
        if youngest_row.empty or youngest_row["rr_mean"].values[0] == 1.0:
            for age in ADULT_AGE_LABELS:
                attenuation[(cause, age)] = 1.0
            continue
        log_rr_youngest = math.log(float(youngest_row["rr_mean"].values[0]))
        if abs(log_rr_youngest) < 1e-10:
            for age in ADULT_AGE_LABELS:
                attenuation[(cause, age)] = 1.0
            continue

        for age in ADULT_AGE_LABELS:
            age_row = cause_data[
                (cause_data["age"] == age) & (cause_data["exposure_g_per_day"] == ref_x)
            ]
            if age_row.empty:
                attenuation[(cause, age)] = 1.0
                continue
            att = math.log(float(age_row["rr_mean"].values[0])) / log_rr_youngest
            attenuation[(cause, age)] = max(0.0, min(1.0, att))

    return attenuation


def _apply_red_meat_log_linear(df: pd.DataFrame) -> pd.DataFrame:
    """Replace the GBD red-meat curve with age-corrected log-linear curves.

    The replacement uses the literature meta-analysis central/CI estimates in
    ``red_meat_rr_log_linear.csv`` (Bechthold 2019, Li 2024, Chan 2011):
    ``RR(x) = exp(att * ln(rr) * x / per_unit)``. The exposure grid and the
    per-(cause, age) attenuation factors are taken from the parsed GBD
    red-meat curve so the model basis and age structure are preserved.
    """
    alt = pd.read_csv(RED_MEAT_RR_CSV)
    attenuation = _extract_age_attenuation(df, "red_meat")
    gbd = df[df["risk_factor"] == "red_meat"]
    if gbd.empty:
        raise ValueError("No GBD red_meat curve parsed; cannot apply log-linear RR")
    exposures = sorted(gbd["exposure_g_per_day"].unique())

    rows: list[dict] = []
    for _, row in alt.iterrows():
        cause = row["outcome"]
        rr_central = float(row["rr_central"])
        rr_lower = float(row["rr_lower_95ci"])
        rr_upper = float(row["rr_upper_95ci"])
        per_unit = _parse_per_unit(row["per_unit"])
        for age in ADULT_AGE_LABELS:
            att = attenuation.get((cause, age), 1.0)
            for exp_g in exposures:
                x_ratio = exp_g / per_unit
                rows.append(
                    {
                        "risk_factor": "red_meat",
                        "cause": cause,
                        "age": age,
                        "exposure_g_per_day": exp_g,
                        "rr_mean": math.exp(att * math.log(rr_central) * x_ratio),
                        "rr_low": math.exp(att * math.log(rr_lower) * x_ratio),
                        "rr_high": math.exp(att * math.log(rr_upper) * x_ratio),
                    }
                )

    df = df[df["risk_factor"] != "red_meat"]
    return pd.concat([df, pd.DataFrame(rows)], ignore_index=True)


def build_relative_risks() -> pd.DataFrame:
    """Parse the GBD 2019 RR workbook into the model-basis dose–response table.

    Covers the five plant groups and processed meat directly from the GBD
    curves; the red-meat curve is then replaced by the literature log-linear
    curve (GBD red meat is used only for its exposure grid and age structure).
    """
    raw = pd.read_excel(GBD_RR_XLSX, header=None)
    diet_rows = [
        i for i, v in raw[0].items() if isinstance(v, str) and v.startswith("Diet")
    ]

    records: list[dict] = []
    for k, start in enumerate(diet_rows):
        name = str(raw.at[start, 0]).strip()
        risk = GBD_RISK_NAMES.get(name)
        if risk is None:
            continue
        end = diet_rows[k + 1] if k + 1 < len(diet_rows) else len(raw)
        factor = RR_BASIS_FACTOR.get(risk, 1.0)
        records.extend(_parse_rr_block(raw, start + 1, end, risk, factor))

    df = pd.DataFrame(records)
    df = _fill_missing_ages(df)
    df = _apply_red_meat_log_linear(df)
    df = df.sort_values(
        ["risk_factor", "cause", "age", "exposure_g_per_day"]
    ).reset_index(drop=True)
    return df


# --------------------------------------------------------------------------
# Mortality (IHME GBD 2023 cause-specific death rates)
# --------------------------------------------------------------------------

# IHME location names pycountry cannot match unambiguously.
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
    "Niger": "NER",  # fuzzy search confuses with Nigeria (NGA)
    "Republic of Korea": "KOR",
    "Republic of Moldova": "MDA",
    "Republic of the Congo": "COG",
    "Saint Barthélemy": "BLM",
    "Saint Martin (French part)": "MAF",
    "Sint Maarten (Dutch part)": "SXM",
    "The former Yugoslav Republic of Macedonia": "MKD",
    "Türkiye": "TUR",
    "United Kingdom of Great Britain and Northern Ireland": "GBR",
    "United Republic of Tanzania": "TZA",
    "United States of America": "USA",
    "United States Virgin Islands": "VIR",
    "Venezuela (Bolivarian Republic of)": "VEN",
    "Viet Nam": "VNM",
}

# IHME cause name -> model cause (mortality sheet uses "Diabetes mellitus").
GBD_MORTALITY_CAUSE_MAP = {
    "Ischemic heart disease": "CHD",
    "Ischemic stroke": "Stroke",
    "Diabetes mellitus": "T2DM",
    "Colon and rectum cancer": "CRC",
}

# IHME age name -> model age bucket (two under-5 bands fold into 1-4).
GBD_AGE_MAP = {
    "<1 year": "<1",
    "12-23 months": "1-4",
    "2-4 years": "1-4",
    "5-9 years": "5-9",
    "10-14 years": "10-14",
    "15-19 years": "15-19",
    "20-24 years": "20-24",
    "25-29 years": "25-29",
    "30-34 years": "30-34",
    "35-39 years": "35-39",
    "40-44 years": "40-44",
    "45-49 years": "45-49",
    "50-54 years": "50-54",
    "55-59 years": "55-59",
    "60-64 years": "60-64",
    "65-69 years": "65-69",
    "70-74 years": "70-74",
    "75-79 years": "75-79",
    "80-84 years": "80-84",
    "85-89 years": "85-89",
    "90-94 years": "90-94",
    "95+ years": "95+",
}

# Territories/dependencies without separate IHME data -> proxy country.
MORTALITY_COUNTRY_PROXIES = {
    "ASM": "WSM",  # American Samoa -> Samoa
    "GUF": "FRA",  # French Guiana -> France
    "PRI": "USA",  # Puerto Rico -> USA
    "SOM": "ETH",  # Somalia -> Ethiopia
}


def _map_country_to_iso3(name: str) -> str | None:
    if name in COUNTRY_NAME_OVERRIDES:
        return COUNTRY_NAME_OVERRIDES[name]
    try:
        matches = pycountry.countries.search_fuzzy(name)
    except LookupError:
        return None
    return matches[0].alpha_3 if matches else None


def build_mortality() -> pd.DataFrame:
    """Per-country cause-specific death rate (per 1,000) for the four causes."""
    df = pd.read_csv(GBD_MORTALITY_CSV)
    df = df[(df["metric_name"] == "Rate") & (df["year"] == REFERENCE_YEAR)].copy()

    country_map = {n: _map_country_to_iso3(n) for n in df["location_name"].unique()}
    df["country"] = df["location_name"].map(country_map)
    df["cause"] = df["cause_name"].map(GBD_MORTALITY_CAUSE_MAP)
    df["age"] = df["age_name"].map(GBD_AGE_MAP)
    df = df.dropna(subset=["country", "cause", "age"])

    # Fold the two under-5 IHME bands into 1-4 (unweighted mean of rates).
    df = df.groupby(["country", "cause", "age"], as_index=False).agg(
        val=("val", "mean")
    )
    df["death_rate_per_1000"] = df["val"] / 100.0  # per 100,000 -> per 1,000

    out = df[["age", "cause", "country", "death_rate_per_1000"]]

    # Fill known territories from a proxy country where IHME lacks them.
    present = set(out["country"])
    proxy_rows = []
    for target, proxy in MORTALITY_COUNTRY_PROXIES.items():
        if target not in present and proxy in present:
            rows = out[out["country"] == proxy].copy()
            rows["country"] = target
            proxy_rows.append(rows)
    if proxy_rows:
        out = pd.concat([out, *proxy_rows], ignore_index=True)

    return out.sort_values(["country", "cause", "age"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# Population (UN WPP)
# --------------------------------------------------------------------------


def build_population() -> pd.DataFrame:
    """Per-country population by age bucket (+ ``all-a`` total), persons, 2020.

    The WPP "Population by 5-year age group" file reports a combined ``0-4``
    band (and ``PopTotal`` is already both sexes), so the under-5 band is
    disaggregated into ``<1`` (20%) and ``1-4`` (80%) and the open-ended
    ``95-99`` / ``100+`` bands are merged into ``95+``.
    """
    df = pd.read_csv(WPP_POPULATION_GZ, compression="gzip", low_memory=False)
    df = df[df["Variant"].astype(str).str.lower() == "medium"]
    df = df[pd.to_numeric(df["Time"], errors="coerce") == REFERENCE_YEAR]
    df = df[df["ISO3_code"].notna()].copy()
    df["ISO3_code"] = df["ISO3_code"].astype(str).str.upper()
    df["PopTotal"] = pd.to_numeric(df["PopTotal"], errors="coerce")
    df = df.dropna(subset=["PopTotal"])
    df["AgeGrpStart"] = pd.to_numeric(df.get("AgeGrpStart"), errors="coerce")
    df["AgeGrpSpan"] = pd.to_numeric(df.get("AgeGrpSpan"), errors="coerce")

    records = []
    for iso3, grp in df.groupby("ISO3_code"):
        buckets: dict[str, float] = {}
        for _, row in grp.iterrows():
            bucket = _wpp_age_bucket(row["AgeGrpStart"], row["AgeGrpSpan"])
            if bucket is None:
                continue
            buckets[bucket] = buckets.get(bucket, 0.0) + float(row["PopTotal"]) * 1000.0

        # Disaggregate a combined 0-4 band into <1 / 1-4 where granular bands
        # are absent (the 5-year-group file always reports only 0-4).
        zero_four = buckets.pop("0-4", 0.0)
        if zero_four > 0.0:
            under_one = buckets.get("<1", 0.0)
            one_to_four = buckets.get("1-4", 0.0)
            remainder = max(zero_four - under_one - one_to_four, 0.0)
            if under_one == 0.0 and one_to_four == 0.0:
                under_one = 0.2 * remainder
                one_to_four = remainder - under_one
            elif under_one == 0.0:
                under_one = remainder
            elif one_to_four == 0.0:
                one_to_four = remainder
            buckets["<1"] = under_one
            buckets["1-4"] = one_to_four

        if not all(b in buckets for b in AGE_BUCKETS):
            continue  # incomplete coverage; dropped by the country intersection
        for age in AGE_BUCKETS:
            records.append({"age": age, "country": iso3, "population": buckets[age]})
        records.append(
            {
                "age": "all-a",
                "country": iso3,
                "population": sum(buckets[a] for a in AGE_BUCKETS),
            }
        )

    out = pd.DataFrame(records)
    out["age"] = pd.Categorical(
        out["age"], categories=[*AGE_BUCKETS, "all-a"], ordered=True
    )
    return out.sort_values(["country", "age"]).reset_index(drop=True)


def _wpp_age_bucket(start: float, span: float) -> str | None:
    """Map a WPP age group (start/span) to a model age bucket (0-4 kept raw)."""
    if pd.isna(start) or pd.isna(span):
        return None
    start, span = int(start), int(span)
    if start == 0 and span == 1:
        return "<1"
    if start == 0 and span in {4, 5}:
        return "0-4"
    if start == 1 and span in {4, 5}:
        return "1-4"
    if 5 <= start <= 90 and span == 5:
        return f"{start}-{start + 4}"
    if start >= 95:
        return "95+"
    return None


# --------------------------------------------------------------------------
# Life table (UN WPP)
# --------------------------------------------------------------------------


def _normalize_wpp_age(label: object) -> str | None:
    text = str(label).strip().lower()
    if text in {"0", "0-0", "<1", "under age 1", "under 1"}:
        return "<1"
    if text in {"1-4", "01-04", "1 to 4"}:
        return "1-4"
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", text)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        if start == 0:
            return "<1"
        if start == 1 and end in {4, 5}:
            return "1-4"
        if start >= 5 and end == start + 4 and start <= 90:
            return f"{start}-{end}"
        if start >= 95:
            return "95+"
    if text in {"95-99", "95+", "100+", "95 plus", "100 plus"}:
        return "95+"
    return None


def build_life_table(countries: set[str]) -> pd.DataFrame:
    """Per-country abridged life table (lx survivors, ex) for both sexes.

    Falls back to the World life table for countries WPP lacks individually.
    The WPP abridged file starts in 2024, so the nearest year is used.
    """
    raw = pd.read_csv(WPP_LIFE_TABLE_GZ, low_memory=False)
    raw = raw[
        (raw["Variant"].astype(str).str.lower() == "medium")
        & (raw["Sex"].astype(str).str.lower() == "total")
    ].copy()
    raw["Time"] = pd.to_numeric(raw["Time"], errors="coerce")
    years = sorted({int(y) for y in raw["Time"].dropna().unique()})
    target_year = (
        REFERENCE_YEAR
        if REFERENCE_YEAR in years
        else min(years, key=lambda y: (abs(y - REFERENCE_YEAR), y))
    )
    if target_year != REFERENCE_YEAR:
        print(f"  life table: year {REFERENCE_YEAR} unavailable; using {target_year}")
    raw = raw[raw["Time"].astype("Int64") == target_year].copy()
    raw["bucket"] = raw["AgeGrp"].map(_normalize_wpp_age)
    raw = raw.dropna(subset=["bucket"])

    def _table_for(df: pd.DataFrame, country: str) -> list[dict] | None:
        seen, recs = set(), []
        for _, r in df.iterrows():
            b = r["bucket"]
            if b in seen:
                continue
            try:
                lx, ex = float(r["lx"]), float(r["ex"])
            except (TypeError, ValueError):
                continue
            seen.add(b)
            recs.append({"country": country, "age": b, "lx": lx, "ex": ex})
        if not all(b in seen for b in AGE_BUCKETS):
            return None
        return recs

    world = raw[raw["Location"].astype(str) == "World"]
    world_recs = _table_for(world, "WORLD")
    if world_recs is None:
        raise RuntimeError("Could not build World life table fallback")

    out_rows: list[dict] = []
    by_iso = {str(k): v for k, v in raw.groupby("ISO3_code")}
    n_fallback = 0
    for c in sorted(countries):
        recs = _table_for(by_iso[c], c) if c in by_iso else None
        if recs is None:
            recs = [{**r, "country": c} for r in world_recs]
            n_fallback += 1
        out_rows.extend(recs)
    print(
        f"  life table: {len(countries) - n_fallback} country-specific, "
        f"{n_fallback} World fallback"
    )

    out = pd.DataFrame(out_rows)
    out["age"] = pd.Categorical(out["age"], categories=AGE_BUCKETS, ordered=True)
    return out.sort_values(["country", "age"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def main() -> None:
    _ensure_raw_downloads()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Building relative_risks.csv ...")
    rr = build_relative_risks()
    print("Building mortality.csv ...")
    mort = build_mortality()
    print("Building population.csv ...")
    pop = build_population()

    # The baseline diet (a separate, bundled dataset) defines the country
    # universe; every diet country must have complete burden inputs.
    baseline_intake = pd.read_csv(OUT_DIR / "baseline_intake.csv")
    diet_countries = set(baseline_intake["country"])

    print("Building life_table.csv ...")
    life = build_life_table(diet_countries)

    complete = set(mort["country"]) & set(pop["country"]) & set(life["country"])
    missing = diet_countries - complete
    if missing:
        raise RuntimeError(
            f"{len(missing)} baseline-diet countries lack complete burden data "
            f"(mortality/population/life table): {sorted(missing)[:20]}"
            f"{'...' if len(missing) > 20 else ''}. The baseline diet and burden "
            "data may be out of sync; refresh the baseline diet too."
        )

    keep = diet_countries
    mort = mort[mort["country"].isin(keep)]
    pop = pop[pop["country"].isin(keep)]
    life = life[life["country"].isin(keep)]
    print(f"Countries with complete data: {len(keep)}")

    rr.to_csv(OUT_DIR / "relative_risks.csv", index=False)
    mort.to_csv(OUT_DIR / "mortality.csv", index=False)
    pop.to_csv(OUT_DIR / "population.csv", index=False)
    life.to_csv(OUT_DIR / "life_table.csv", index=False)

    print("\nWrote:")
    for name, df in [
        ("relative_risks", rr),
        ("mortality", mort),
        ("population", pop),
        ("life_table", life),
    ]:
        print(f"  {name}.csv: {len(df)} rows")


if __name__ == "__main__":
    main()
