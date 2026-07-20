# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Loaders for the bundled, processed data.

The package ships small processed CSVs derived from GBD, GDD-IA and UN WPP
(see ``docs/model/data_sources.md`` for provenance and licensing). All loaders are
cached so the files are read once per process.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

import numpy as np
import pandas as pd

from .foodgroups import (
    ADULT_AGES,
    AGE_BUCKETS,
    CAUSES,
    DIRECT_NUTRIENT_FACTORS,
    RISK_FACTORS,
)


def _read(name: str) -> pd.DataFrame:
    # The bundled CSVs live in the ``data/`` directory of the package. We
    # reference the package root (not ``mealhealth.data``, which would collide
    # with this module's own name) and descend into ``data/``.
    resource = resources.files("mealhealth").joinpath("data").joinpath(name)
    with resources.as_file(resource) as path:
        return pd.read_csv(path)


@lru_cache(maxsize=1)
def relative_risks() -> pd.DataFrame:
    """risk_factor, cause, age, exposure_g_per_day, rr_mean, rr_low, rr_high."""
    return _read("relative_risks.csv")


@lru_cache(maxsize=1)
def baseline_exposure() -> pd.DataFrame:
    """Complete direct-factor baseline, including omega-3 and provenance."""
    df = _read("baseline_exposure.csv")
    expected_columns = {
        "country",
        "risk_factor",
        "exposure_g_per_day",
        "source_country",
        "source_year",
    }
    if set(df.columns) != expected_columns:
        raise ValueError("Invalid bundled baseline_exposure.csv schema")
    countries = set(df["country"])
    expected = {
        (country, risk)
        for country in countries
        for risk in (*RISK_FACTORS, *DIRECT_NUTRIENT_FACTORS)
    }
    rows = list(df[["country", "risk_factor"]].itertuples(index=False, name=None))
    if len(rows) != len(set(rows)) or set(rows) != expected:
        raise ValueError("Invalid direct baseline country/risk-factor coverage")
    values = pd.to_numeric(df["exposure_g_per_day"], errors="coerce")
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Bundled direct exposures must be finite and non-negative")
    if set(df["source_year"]) != {2020}:
        raise ValueError("Bundled direct exposures must use source_year 2020")
    expected_sources = df["country"].where(df["country"] != "GUF", "FRA")
    if not df["source_country"].equals(expected_sources):
        raise ValueError(
            "Bundled direct exposure source_country must be direct except GUF->FRA"
        )
    return df


@lru_cache(maxsize=1)
def baseline_calories() -> pd.DataFrame:
    """country, kcal_per_day (total baseline daily energy)."""
    df = _read("baseline_calories.csv")
    if set(df.columns) == {
        "country",
        "calories_kcal_per_day",
        "source_country",
        "source_year",
    }:
        df = df.rename(columns={"calories_kcal_per_day": "kcal_per_day"})
    expected = {"country", "kcal_per_day", "source_country", "source_year"}
    if set(df.columns) != expected or len(df) != len(set(df["country"])):
        raise ValueError("Invalid bundled baseline_calories.csv schema")
    if set(df["source_year"]) != {2020}:
        raise ValueError("Bundled calorie baselines must use source_year 2020")
    values = pd.to_numeric(df["kcal_per_day"], errors="coerce")
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Bundled calories must be finite and non-negative")
    return df


@lru_cache(maxsize=1)
def baseline_mediators() -> pd.DataFrame:
    """Country-age-sex mean urinary sodium and SBP exposure summaries.

    The ``lower`` and ``upper`` columns are GBD uncertainty bounds on each
    modeled stratum mean.  They do not describe the distribution of exposure
    between people within the stratum.
    """
    df = _read("baseline_mediators.csv")
    value_columns = [
        "sodium_urinary_g_per_day_mean",
        "sodium_urinary_g_per_day_lower",
        "sodium_urinary_g_per_day_upper",
        "sbp_mmhg_mean",
        "sbp_mmhg_lower",
        "sbp_mmhg_upper",
    ]
    expected_columns = {
        "country",
        "age",
        "sex",
        *value_columns,
        "source_country",
        "source_year",
    }
    if set(df.columns) != expected_columns:
        raise ValueError(
            "Invalid bundled baseline_mediators.csv schema: expected "
            f"{sorted(expected_columns)}, got {sorted(df.columns)}"
        )

    countries = set(baseline_exposure()["country"])
    ages = {
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
    }
    expected = {
        (country, age, sex)
        for country in countries
        for age in ages
        for sex in ("male", "female")
    }
    rows = list(df[["country", "age", "sex"]].itertuples(index=False, name=None))
    actual = set(rows)
    if len(rows) != len(actual) or actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            "Invalid bundled mediator baseline coverage: "
            f"missing={missing[:10]}, extra={extra[:10]}, duplicates="
            f"{len(rows) - len(actual)}"
        )

    values = df[value_columns].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(values.to_numpy(dtype=float)).all() or (values < 0).any(
        axis=None
    ):
        raise ValueError("Bundled mediator baselines must be finite and non-negative")
    for prefix in ("sodium_urinary_g_per_day", "sbp_mmhg"):
        if (
            (values[f"{prefix}_lower"] > values[f"{prefix}_mean"])
            | (values[f"{prefix}_mean"] > values[f"{prefix}_upper"])
        ).any():
            raise ValueError(f"Invalid {prefix} uncertainty ordering")
    if set(df["source_year"]) != {2020}:
        raise ValueError("Bundled mediator baselines must use source_year 2020")
    expected_sources = df["country"].where(df["country"] != "GUF", "FRA")
    if not df["source_country"].equals(expected_sources):
        raise ValueError(
            "Bundled mediator source_country must be direct except GUF->FRA"
        )
    return df


@lru_cache(maxsize=1)
def sodium_relative_risks() -> pd.DataFrame:
    """All-age GBD 2023 BoP curves for the sodium and SBP paths."""

    df = _read("sodium_relative_risks.csv")
    expected_columns = {
        "path",
        "curve_cause",
        "exposure",
        "rr_mean",
        "rr_low",
        "rr_high",
        "risk_lower",
        "risk_upper",
        "star_rating",
        "rei_id",
        "cause_id",
    }
    if set(df.columns) != expected_columns:
        raise ValueError("Invalid bundled sodium_relative_risks.csv schema")
    expected_curves = {
        ("sbp", "CHD"),
        ("sbp", "Stroke"),
        ("sbp", "CKD"),
        ("sodium", "StomachCancer"),
    }
    curves = set(df[["path", "curve_cause"]].itertuples(index=False, name=None))
    if curves != expected_curves:
        raise ValueError("Invalid bundled sodium curve coverage")
    numeric = df[
        [
            "exposure",
            "rr_mean",
            "rr_low",
            "rr_high",
            "risk_lower",
            "risk_upper",
            "star_rating",
            "rei_id",
            "cause_id",
        ]
    ].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError("Bundled sodium relative risks must be finite")
    if (
        (numeric["rr_low"] <= 0)
        | (numeric["rr_low"] > numeric["rr_mean"])
        | (numeric["rr_mean"] > numeric["rr_high"])
    ).any():
        raise ValueError("Invalid bundled sodium RR uncertainty ordering")
    for pair, group in df.groupby(["path", "curve_cause"], sort=False):
        exposure = group["exposure"].to_numpy(dtype=float)
        if len(exposure) < 2 or not np.all(np.diff(exposure) > 0):
            raise ValueError(f"Invalid sodium exposure grid for {pair}")
    return df


@lru_cache(maxsize=1)
def sbp_age_attenuation() -> pd.DataFrame:
    """GBD 2019 log-RR age shape, normalized to age 60--64."""

    df = _read("sbp_age_attenuation.csv")
    if set(df.columns) != {"curve_cause", "age", "beta"}:
        raise ValueError("Invalid bundled sbp_age_attenuation.csv schema")
    causes = {"CHD", "Stroke", "CKD"}
    expected = {(cause, age) for cause in causes for age in ADULT_AGES}
    rows = list(df[["curve_cause", "age"]].itertuples(index=False, name=None))
    if len(rows) != len(set(rows)) or set(rows) != expected:
        raise ValueError("Invalid bundled SBP age-attenuation coverage")
    beta = pd.to_numeric(df["beta"], errors="coerce")
    if not np.isfinite(beta).all() or (beta <= 0).any():
        raise ValueError("SBP age attenuation must be finite and positive")
    reference = df[df["age"] == "60-64"]
    if not np.allclose(reference["beta"], 1.0):
        raise ValueError("SBP age attenuation must be normalized at 60-64")
    return df


@lru_cache(maxsize=1)
def mortality() -> pd.DataFrame:
    """WHO GHE sex-specific cause mortality rates."""
    df = _read("mortality.csv")
    if set(df.columns) != {
        "age",
        "sex",
        "cause",
        "country",
        "source_country",
        "death_rate_per_1000",
    }:
        raise ValueError("Invalid bundled mortality.csv schema")
    countries = set(baseline_exposure()["country"])
    expected = {
        (country, sex, cause, age)
        for country in countries
        for sex in ("male", "female")
        for cause in CAUSES
        for age in AGE_BUCKETS
    }
    rows = list(
        df[["country", "sex", "cause", "age"]].itertuples(index=False, name=None)
    )
    if len(rows) != len(set(rows)) or set(rows) != expected:
        raise ValueError("Invalid bundled mortality stratum coverage")
    rates = pd.to_numeric(df["death_rate_per_1000"], errors="coerce")
    if not np.isfinite(rates).all() or (rates < 0).any():
        raise ValueError("Bundled mortality rates must be finite and non-negative")
    source_pairs = set(
        df[["country", "source_country"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    expected_proxies = {
        ("ASM", "WSM"),
        ("GUF", "FRA"),
        ("PRI", "USA"),
        ("PSE", "JOR"),
        ("TWN", "KOR"),
    }
    proxies = {
        (country, source) for country, source in source_pairs if country != source
    }
    if proxies != expected_proxies:
        raise ValueError("Invalid bundled mortality country provenance")
    return df


@lru_cache(maxsize=1)
def population() -> pd.DataFrame:
    """age, sex, country, population (persons)."""
    df = _read("population.csv")
    if set(df.columns) != {"age", "sex", "country", "population"}:
        raise ValueError("Invalid bundled population.csv schema")
    countries = set(baseline_exposure()["country"])
    expected = {
        (country, sex, age)
        for country in countries
        for sex in ("male", "female")
        for age in (*AGE_BUCKETS, "all-a")
    }
    rows = list(df[["country", "sex", "age"]].itertuples(index=False, name=None))
    if len(rows) != len(set(rows)) or set(rows) != expected:
        raise ValueError("Invalid bundled population stratum coverage")
    values = pd.to_numeric(df["population"], errors="coerce")
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Bundled population must be finite and non-negative")
    return df


@lru_cache(maxsize=1)
def local_life_table() -> pd.DataFrame:
    """Country/sex local lx survivors and ex remaining life expectancy."""
    df = _read("local_life_table.csv")
    if set(df.columns) != {"country", "sex", "age", "lx", "ex"}:
        raise ValueError("Invalid bundled local_life_table.csv schema")
    countries = set(baseline_exposure()["country"])
    expected = {
        (country, sex, age)
        for country in countries
        for sex in ("male", "female")
        for age in AGE_BUCKETS
    }
    rows = list(df[["country", "sex", "age"]].itertuples(index=False, name=None))
    if len(rows) != len(set(rows)) or set(rows) != expected:
        raise ValueError("Invalid bundled local-life-table stratum coverage")
    values = df[["lx", "ex"]].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(values.to_numpy()).all() or (values < 0).any(axis=None):
        raise ValueError("Bundled life-table values must be finite and non-negative")
    return df


@lru_cache(maxsize=1)
def standard_life_table() -> pd.DataFrame:
    """age, ex (GBD 2023 theoretical-minimum-risk life expectancy)."""
    return _read("standard_life_table.csv")


@lru_cache(maxsize=1)
def available_countries() -> list[str]:
    """ISO3 codes with complete bundled data, sorted."""
    return sorted(baseline_exposure()["country"].unique())
