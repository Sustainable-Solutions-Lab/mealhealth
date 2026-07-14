#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build the bundled baseline-diet CSVs. **TEMPORARY** — see note below.

``mealhealth`` ships a per-country baseline diet under ``src/mealhealth/data/``:

- ``baseline_intake.csv``   country, risk_factor, intake_g_per_day
- ``baseline_calories.csv`` country, kcal_per_day

Unlike the health/demographic data (which ``tools/prepare_data.py`` regenerates
from public raw sources), the baseline diet is a *derived research product*. It
is currently produced from the sibling **GLADE** project (the Global Land,
Agriculture, Diet and Emissions model) — its processed
dietary intake (GDD-IA / NHANES, with the unprocessed/processed red-meat split
from the GDD-IA processed fraction). That dataset is openly available during
development but is **not** part of ``mealhealth``'s self-contained pipeline.

  TODO: replace this tool with a download from the published Zenodo dataset
  once available (set ``BASELINE_DIET_SOURCE`` / ``docs/data_sources.md``).

The committed ``baseline_intake.csv`` / ``baseline_calories.csv`` are the
canonical artifacts; this script only needs to be re-run if the baseline diet
itself changes. It is intentionally the only tool that references GLADE.

Run with GLADE's environment, e.g.::

    cd /path/to/glade
    .pixi/envs/default/bin/python /path/to/mealhealth/tools/baseline_diet_from_glade.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Path to a GLADE checkout (the temporary baseline-diet source). The directory
# may be capitalised or not; pick whichever exists. Future: a Zenodo DOI / URL
# once the baseline diet is published.
_GLADE_CANDIDATES = (
    Path("/home/koen/Dokument/Research/Code/GLADE"),
    Path("/home/koen/Dokument/Research/Code/glade"),
)
GLADE = next((p for p in _GLADE_CANDIDATES if p.exists()), _GLADE_CANDIDATES[0])
RUN = "central"  # canonical GLADE processing run

OUT_DIR = Path(__file__).resolve().parent.parent / "src" / "mealhealth" / "data"

PLANT_RISKS = ["fruits", "vegetables", "whole_grains", "legumes", "nuts_seeds"]


def _gdd_processed_fraction() -> pd.Series:
    """Per-country processed-meat fraction phi = prc_meat / (prc_meat + red_meat).

    Uses GDD-IA 'prcd' meat categories (baseline strata: all-ages, both sexes,
    all residences, mean), which natively separate processed from unprocessed
    red meat.
    """
    grams = pd.read_csv(
        GLADE / "data" / "manually_downloaded" / "GDD-IA-intake_grams_2020.csv"
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

    Plant groups and the combined red-meat total come from GLADE's validated
    ``dietary_intake.csv`` (USA = NHANES override, others = GDD-IA). The combined
    red-meat total is then split into unprocessed ``red_meat`` and
    ``processed_meat`` using the GDD-IA processed fraction (global median where a
    country lacks the GDD-IA split).
    """
    diet = pd.read_csv(GLADE / "processing" / RUN / "dietary_intake.csv")
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
    return out.sort_values(["country", "risk_factor"]).reset_index(drop=True)


def build_baseline_calories() -> pd.DataFrame:
    """Total baseline daily energy per country (kcal/person/day) from GDD-IA."""
    tgt = pd.read_csv(GLADE / "processing" / RUN / "gdd_ia_kcal_target.csv")
    out = tgt[["country", "kcal_all_fg"]].rename(
        columns={"kcal_all_fg": "kcal_per_day"}
    )
    return out.sort_values("country").reset_index(drop=True)


def _burden_country_set() -> set[str]:
    """Countries with complete burden inputs in GLADE's processed data.

    Restricting the baseline diet to this set keeps it consistent with the
    burden data regenerated by ``tools/prepare_data.py`` (every diet country
    must have mortality + population coverage).
    """
    mort = pd.read_csv(
        GLADE / "processing" / RUN / "health" / "gbd_mortality_rates.csv",
        header=None,
        names=["age", "cause", "country", "year", "value"],
    )
    pop = pd.read_csv(GLADE / "processing" / RUN / "population_age.csv")
    return set(mort["country"]) & set(pop["country"])


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Building baseline_intake.csv ...")
    intake = build_baseline_intake()
    print("Building baseline_calories.csv ...")
    cal = build_baseline_calories()

    countries = set(intake["country"]) & set(cal["country"]) & _burden_country_set()
    intake = intake[intake["country"].isin(countries)]
    cal = cal[cal["country"].isin(countries)]
    print(f"Baseline-diet countries: {len(countries)}")

    intake.to_csv(OUT_DIR / "baseline_intake.csv", index=False)
    cal.to_csv(OUT_DIR / "baseline_calories.csv", index=False)

    print("\nUSA red/processed split & calories:")
    print(intake[intake["country"] == "USA"].to_string(index=False))
    print(cal[cal["country"] == "USA"].to_string(index=False))


if __name__ == "__main__":
    main()
