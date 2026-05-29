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

import pandas as pd


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
