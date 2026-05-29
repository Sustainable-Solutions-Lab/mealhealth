#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Derive the minimal bundled data for ``mealhealth`` from the food-opt project.

This is a *one-time* developer tool, not part of the installed package. It
reads the raw and processed inputs of the sibling ``food-opt`` project and
writes the small, processed CSVs that ``mealhealth`` ships under
``src/mealhealth/data/``.

The package as distributed contains only *processed / adapted* derivatives of
GBD, GDD-IA and UN WPP data, reduced to the minimum needed to evaluate the
health-impact formulas. The underlying raw datasets (IHME GBD mortality and
relative risks, GDD-IA dietary intake) are *not* redistributable and are not
copied; see ``docs/data_sources.md``.

Outputs (schemas documented in ``src/mealhealth/data/DATA_PROVENANCE.md``):

- ``relative_risks.csv``   risk_factor, cause, age, exposure_g_per_day,
                           rr_mean, rr_low, rr_high   (model/fresh basis)
- ``baseline_intake.csv``  country, risk_factor, intake_g_per_day
- ``baseline_calories.csv``country, kcal_per_day
- ``mortality.csv``        age, cause, country, death_rate_per_1000
- ``population.csv``        age, country, population
- ``life_table.csv``       country, age, lx, ex

Run with food-opt's environment, e.g.::

    cd /path/to/food-opt
    .pixi/envs/default/bin/python /path/to/meal-health-indicator/tools/prepare_data.py
"""

from __future__ import annotations

import math
from pathlib import Path
import re

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

FOODOPT = Path("/home/koen/Dokument/Research/Code/food-opt")
RUN = "central"  # canonical food-opt processing run
REFERENCE_YEAR = 2020

OUT_DIR = Path(__file__).resolve().parent.parent / "src" / "mealhealth" / "data"

# Risk factors and causes (subset of food-opt, plus processed_meat).
PLANT_RISKS = ["fruits", "vegetables", "whole_grains", "legumes", "nuts_seeds"]
CAUSES = ["CHD", "Stroke", "T2DM", "CRC"]

# Conversion of meat RR-curve x-axis and intakes from GBD/GDD "as-consumed"
# (cooked) basis to the model's fresh retail basis. Matches
# food-opt weight_conversion.cooked_to_fresh.red_meat.
MEAT_COOKED_TO_FRESH = 1.43

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

GBD_CAUSE_MAP = {
    "Ischemic heart disease": "CHD",
    "Ischemic stroke": "Stroke",
    "Diabetes mellitus type 2": "T2DM",
    "Colon and rectum cancer": "CRC",
}

_NUM = re.compile(r"[-+]?(?:\d+\.\d+|\d+)")


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


def parse_gbd_processed_meat(xlsx: Path) -> pd.DataFrame:
    """Extract the 'Diet high in processed meat' RR curves from the GBD XLSX.

    Returns tidy rows with exposure converted to the model fresh basis.
    GBD maps processed meat to CHD (IHD), T2DM and CRC (no stroke).
    """
    raw = pd.read_excel(xlsx, header=None)
    diet_rows = [
        i for i, v in raw[0].items() if isinstance(v, str) and v.startswith("Diet")
    ]
    target = [i for i in diet_rows if "processed meat" in str(raw.at[i, 0]).lower()]
    if not target:
        raise RuntimeError("No 'Diet high in processed meat' block in GBD XLSX")
    start = target[0]
    later = [r for r in diet_rows if r > start]
    end = later[0] if later else len(raw)

    records = []
    for _, row in raw.iloc[start + 1 : end].iterrows():
        outcome = row[0]
        exposure = row[1]
        if not isinstance(outcome, str) or not isinstance(exposure, str):
            continue
        if outcome not in GBD_CAUSE_MAP:
            continue
        cause = GBD_CAUSE_MAP[outcome]
        m = re.match(r"\s*([0-9.]+)\s*g/day", exposure)
        if not m:
            continue
        exp_g = float(m.group(1)) * MEAT_COOKED_TO_FRESH
        for col, age in ADULT_AGE_COLUMNS.items():
            if col >= len(row):
                continue
            parsed = _parse_rr_cell(row[col])
            if parsed is None:
                continue
            mean, low, high = parsed
            records.append(
                {
                    "risk_factor": "processed_meat",
                    "cause": cause,
                    "age": age,
                    "exposure_g_per_day": exp_g,
                    "rr_mean": mean,
                    "rr_low": low,
                    "rr_high": high,
                }
            )
    df = pd.DataFrame(records)
    df = _fill_missing_ages(df)
    return df


def build_relative_risks() -> pd.DataFrame:
    """Plant groups + red_meat from food-opt; processed_meat from GBD XLSX."""
    rr = pd.read_csv(FOODOPT / "processing" / RUN / "health" / "relative_risks.csv")
    keep = PLANT_RISKS + ["red_meat"]
    rr = rr[rr["risk_factor"].isin(keep)].copy()

    pm = parse_gbd_processed_meat(
        FOODOPT
        / "data"
        / "manually_downloaded"
        / "IHME_GBD_2019_RELATIVE_RISKS_Y2020M10D15.XLSX"
    )
    out = pd.concat([rr, pm], ignore_index=True)
    out = out.sort_values(
        ["risk_factor", "cause", "age", "exposure_g_per_day"]
    ).reset_index(drop=True)
    return out


# --------------------------------------------------------------------------
# Baseline diet (intakes + calories)
# --------------------------------------------------------------------------


def _gdd_processed_fraction() -> pd.Series:
    """Per-country processed-meat fraction phi = prc_meat / (prc_meat + red_meat).

    Uses GDD-IA 'prcd' meat categories (baseline strata: all-ages, both sexes,
    all residences, mean), which natively separate processed from unprocessed
    red meat.
    """
    grams = pd.read_csv(
        FOODOPT / "data" / "manually_downloaded" / "GDD-IA-intake_grams_2020.csv"
    )
    mask = (
        (grams["age"] == "all-a")
        & (grams["sex"] == "BTH")
        & (grams["residence"] == "all-u")
        & (grams["stats"] == "mean")
        & (grams["type"] == "prcd")
        & (grams["food_group"].isin(["red_meat", "prc_meat"]))
    )
    sub = grams.loc[mask]
    piv = sub.pivot_table(
        index="region", columns="food_group", values="value", aggfunc="sum"
    ).fillna(0.0)
    denom = piv.get("red_meat", 0.0) + piv.get("prc_meat", 0.0)
    phi = (piv.get("prc_meat", 0.0) / denom).where(denom > 0, np.nan)
    phi.name = "phi"
    return phi


def build_baseline_intake() -> pd.DataFrame:
    """Per-country baseline intakes for the 7 risk groups (model/fresh basis).

    Plant groups and the combined red-meat total come from food-opt's
    validated ``dietary_intake.csv`` (USA = NHANES override, others = GDD-IA).
    The combined red-meat total is then split into unprocessed ``red_meat`` and
    ``processed_meat`` using the GDD-IA processed fraction (global median where
    a country lacks the GDD-IA split).
    """
    diet = pd.read_csv(FOODOPT / "processing" / RUN / "dietary_intake.csv")
    diet = diet[diet["item"].isin(PLANT_RISKS + ["red_meat"])].copy()
    diet["value"] = pd.to_numeric(diet["value"], errors="coerce")

    phi = _gdd_processed_fraction()
    phi_default = float(phi.median())

    rows = []
    for country, grp in diet.groupby("country"):
        by_item = grp.set_index("item")["value"].to_dict()
        for r in PLANT_RISKS:
            if r in by_item:
                rows.append((country, r, float(by_item[r])))
        red_total = float(by_item.get("red_meat", 0.0))
        f = phi.get(country, np.nan)
        if not np.isfinite(f):
            f = phi_default
        rows.append((country, "red_meat", red_total * (1.0 - f)))
        rows.append((country, "processed_meat", red_total * f))

    out = pd.DataFrame(rows, columns=["country", "risk_factor", "intake_g_per_day"])
    out = out.sort_values(["country", "risk_factor"]).reset_index(drop=True)
    return out


def build_baseline_calories() -> pd.DataFrame:
    """Total baseline daily energy per country (kcal/person/day) from GDD-IA."""
    tgt = pd.read_csv(FOODOPT / "processing" / RUN / "gdd_ia_kcal_target.csv")
    out = tgt[["country", "kcal_all_fg"]].rename(
        columns={"kcal_all_fg": "kcal_per_day"}
    )
    return out.sort_values("country").reset_index(drop=True)


# --------------------------------------------------------------------------
# Burden inputs (mortality, population, life table)
# --------------------------------------------------------------------------


def build_mortality() -> pd.DataFrame:
    mort = pd.read_csv(
        FOODOPT / "processing" / RUN / "health" / "gbd_mortality_rates.csv",
        header=None,
        names=["age", "cause", "country", "year", "value"],
    )
    mort = mort[(mort["cause"].isin(CAUSES)) & (mort["year"] == REFERENCE_YEAR)]
    out = mort[["age", "cause", "country", "value"]].rename(
        columns={"value": "death_rate_per_1000"}
    )
    return out.sort_values(["country", "cause", "age"]).reset_index(drop=True)


def build_population() -> pd.DataFrame:
    pop = pd.read_csv(FOODOPT / "processing" / RUN / "population_age.csv")
    pop = pop[pop["year"] == REFERENCE_YEAR]
    out = pop[["age", "country", "value"]].rename(columns={"value": "population"})
    return out.sort_values(["country", "age"]).reset_index(drop=True)


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
    """Per-country abridged life table (lx survivors, ex) for both sexes, 2020.

    Falls back to the World life table for countries WPP lacks individually.
    """
    raw = pd.read_csv(
        FOODOPT / "data" / "downloads" / "WPP_life_table.csv.gz", low_memory=False
    )
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
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Building relative_risks.csv ...")
    rr = build_relative_risks()
    print("Building baseline_intake.csv ...")
    intake = build_baseline_intake()
    print("Building baseline_calories.csv ...")
    cal = build_baseline_calories()
    print("Building mortality.csv ...")
    mort = build_mortality()
    print("Building population.csv ...")
    pop = build_population()

    # Country set: intersection of all per-country sources so every bundled
    # country can be fully evaluated in population mode.
    countries = (
        set(intake["country"])
        & set(cal["country"])
        & set(mort["country"])
        & set(pop["country"])
    )
    print("Building life_table.csv ...")
    life = build_life_table(countries)
    countries &= set(life["country"])
    print(f"Countries with complete data: {len(countries)}")

    intake = intake[intake["country"].isin(countries)]
    cal = cal[cal["country"].isin(countries)]
    mort = mort[mort["country"].isin(countries)]
    pop = pop[pop["country"].isin(countries)]
    life = life[life["country"].isin(countries)]

    rr.to_csv(OUT_DIR / "relative_risks.csv", index=False)
    intake.to_csv(OUT_DIR / "baseline_intake.csv", index=False)
    cal.to_csv(OUT_DIR / "baseline_calories.csv", index=False)
    mort.to_csv(OUT_DIR / "mortality.csv", index=False)
    pop.to_csv(OUT_DIR / "population.csv", index=False)
    life.to_csv(OUT_DIR / "life_table.csv", index=False)

    print("\nWrote:")
    for name, df in [
        ("relative_risks", rr),
        ("baseline_intake", intake),
        ("baseline_calories", cal),
        ("mortality", mort),
        ("population", pop),
        ("life_table", life),
    ]:
        print(f"  {name}.csv: {len(df)} rows")
    print("\nUSA red/processed split & calories:")
    print(intake[intake["country"] == "USA"].to_string(index=False))
    print(cal[cal["country"] == "USA"].to_string(index=False))


if __name__ == "__main__":
    main()
