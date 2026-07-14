# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Loaders for the bundled, processed data.

The package ships small processed CSVs derived from GBD, GDD-IA and UN WPP
(see ``docs/data_sources.md`` for provenance and licensing). All loaders are
cached so the files are read once per process.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

import numpy as np
import pandas as pd

from .foodgroups import NUTRIENT_FACTORS


def _read(name: str) -> pd.DataFrame:
    # The bundled CSVs live in the ``data/`` directory of the package. We
    # reference the package root (not ``mealhealth.data``, which would collide
    # with this module's own name) and descend into ``data/``.
    resource = resources.files("mealhealth").joinpath("data", name)
    with resources.as_file(resource) as path:
        return pd.read_csv(path)


@lru_cache(maxsize=1)
def relative_risks() -> pd.DataFrame:
    """risk_factor, cause, age, exposure_g_per_day, rr_mean, rr_low, rr_high."""
    return _read("relative_risks.csv")


@lru_cache(maxsize=1)
def baseline_intake() -> pd.DataFrame:
    """country, risk_factor, intake_g_per_day (model/fresh basis)."""
    return _read("baseline_intake.csv")


@lru_cache(maxsize=1)
def baseline_calories() -> pd.DataFrame:
    """country, kcal_per_day (total baseline daily energy)."""
    return _read("baseline_calories.csv")


@lru_cache(maxsize=1)
def baseline_nutrients() -> pd.DataFrame:
    """country, nutrient, intake_g_per_day, source_country, source_year.

    Every supported country must have exactly one finite, non-negative row for
    every implemented nutrient. This strict load-time check prevents a missing
    baseline from silently becoming a real zero exposure.
    """
    df = _read("baseline_nutrients.csv")
    expected_columns = {
        "country",
        "nutrient",
        "intake_g_per_day",
        "source_country",
        "source_year",
    }
    if set(df.columns) != expected_columns:
        raise ValueError(
            "Invalid bundled baseline_nutrients.csv schema: expected "
            f"{sorted(expected_columns)}, got {sorted(df.columns)}"
        )
    countries = set(baseline_intake()["country"])
    expected = {(c, n) for c in countries for n in NUTRIENT_FACTORS}
    pairs = list(df[["country", "nutrient"]].itertuples(index=False, name=None))
    actual = set(pairs)
    if len(pairs) != len(actual) or actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            "Invalid bundled nutrient baseline coverage: "
            f"missing={missing[:10]}, extra={extra[:10]}, duplicates="
            f"{len(pairs) - len(actual)}"
        )
    values = pd.to_numeric(df["intake_g_per_day"], errors="coerce")
    if not np.isfinite(values.to_numpy(dtype=float)).all() or not (values >= 0).all():
        raise ValueError("Bundled nutrient baselines must be finite and non-negative")
    if set(df["source_year"]) != {2020}:
        raise ValueError("Bundled nutrient baselines must use source_year 2020")
    expected_sources = df["country"].where(df["country"] != "GUF", "FRA")
    if not df["source_country"].equals(expected_sources):
        raise ValueError(
            "Bundled nutrient baseline source_country must be direct except GUF->FRA"
        )
    return df


@lru_cache(maxsize=1)
def mortality() -> pd.DataFrame:
    """age, cause, country, death_rate_per_1000."""
    return _read("mortality.csv")


@lru_cache(maxsize=1)
def population() -> pd.DataFrame:
    """age, country, population (persons)."""
    return _read("population.csv")


@lru_cache(maxsize=1)
def life_table() -> pd.DataFrame:
    """country, age, lx (survivors, radix 100000), ex (remaining life exp.)."""
    return _read("life_table.csv")


@lru_cache(maxsize=1)
def available_countries() -> list[str]:
    """ISO3 codes with complete bundled data, sorted."""
    return sorted(baseline_intake()["country"].unique())
