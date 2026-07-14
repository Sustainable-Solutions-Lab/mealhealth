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

- ``relative_risks.csv``  GBD 2023 Burden-of-Proof dose–response curves
                          (model basis): risk_factor, cause, age,
                          exposure_g_per_day, rr_mean, rr_low, rr_high
- ``mortality.csv``       GBD 2023 cause-specific death rates:
                          age, cause, country, death_rate_per_1000
- ``population.csv``      UN WPP population by age: age, country, population
- ``local_life_table.csv``
                          UN WPP abridged life table: country, age, lx, ex
- ``standard_life_table.csv``
                          GBD 2023 theoretical minimum-risk life expectancy:
                          age, ex

Raw inputs live under ``data/raw/`` (see ``docs/data_sources.md`` for how to
obtain each one). The two UN WPP files and the GBD 2023 Burden-of-Proof RR
curves are fetched automatically; the GBD 2023 cause-specific death-rate CSV
and theoretical minimum-risk life table require a (free) IHME account and must
be downloaded manually beforehand. The relative-risk age structure and TMRELs
come from curated tables under ``tools/reference/`` (see
``tools/generate_rr_age_attenuation.py``).

The *baseline diet* (``baseline_intake.csv``, ``baseline_calories.csv``) is a
separate dataset and is **not** built here — see
``tools/baseline_diet_from_glade.py`` and ``docs/data_sources.md``.

Run from the repository root with the dev environment::

    python tools/prepare_data.py
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
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
GBD_MORTALITY_CSV = RAW_DIR / f"IHME-GBD_2023-death-rates-{REFERENCE_YEAR}.csv"
GBD_REFERENCE_LIFE_TABLE_CSV = (
    RAW_DIR / "IHME_GBD_2023_DEMOGRAPHICS_1950_2023_TMRLT_Y2025M06D09.CSV"
)
WPP_POPULATION_GZ = RAW_DIR / "WPP_population.csv.gz"
WPP_LIFE_TABLE_GZ = RAW_DIR / "WPP_life_table.csv.gz"
# Cached GBD 2023 Burden-of-Proof dose-response curves (fetched automatically,
# no login; one row per curve point in the GBD intake basis). Gitignored.
BOP_CURVES_CSV = RAW_DIR / "bop_rr_curves.csv"

# Bundled curated regeneration inputs (tools/reference/):
#   red-meat literature dose-response curve, the GBD 2023 TMREL table, and the
#   age-attenuation ratios (GBD 2019 age structure, normalized to 60-64).
RED_MEAT_RR_CSV = REFERENCE_DIR / "red_meat_rr_log_linear.csv"
RR_TMREL_CSV = REFERENCE_DIR / "rr_tmrel.csv"
RR_AGE_ATTENUATION_CSV = REFERENCE_DIR / "rr_age_attenuation.csv"

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

# IHME Burden-of-Proof JSON API (GBD 2023 dietary exposure-response curves).
# No login required: the endpoints sit behind Cloudflare's edge bot-check only,
# which a normal browser User-Agent passes. (Automated cloud IPs may get a 403;
# in that case run this once from a normal machine — the curves are cached.)
BOP_API_BASE = "https://vizhub.healthdata.org/burden-of-proof/api/v1"
BOP_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0"
)

# Stable GBD identifiers driving the Burden-of-Proof retrieval.
GBD_REI_ID: dict[str, int] = {
    "fruits": 111,
    "vegetables": 112,
    "whole_grains": 113,
    "legumes": 333,
    "nuts_seeds": 114,
    "red_meat": 116,
    "processed_meat": 117,
    "omega3": 121,
}
GBD_CAUSE_ID: dict[str, int] = {
    "CHD": 493,  # Ischemic heart disease
    "Stroke": 495,  # Ischemic stroke
    "T2DM": 976,  # Diabetes mellitus type 2
    "CRC": 441,  # Colon and rectum cancer
}

# Risk factor -> causes it affects, per GBD 2023 Burden of Proof. nuts_seeds no
# longer links to T2DM (absent in GBD 2023); processed_meat has no ischemic
# stroke curve. red_meat keeps a literature override (see ALTERNATIVE_RR).
RISK_CAUSE_MAP: dict[str, list[str]] = {
    "fruits": ["CHD", "Stroke", "T2DM"],
    "vegetables": ["CHD", "Stroke"],
    "whole_grains": ["CHD", "Stroke", "T2DM", "CRC"],
    "legumes": ["CHD"],
    "nuts_seeds": ["CHD"],
    "red_meat": ["CHD", "Stroke", "T2DM", "CRC"],
    "processed_meat": ["CHD", "T2DM", "CRC"],
    "omega3": ["CHD"],
}

# Risks whose BoP dose-response is replaced by a log-linear literature curve.
ALTERNATIVE_RR: dict[str, Path] = {"red_meat": RED_MEAT_RR_CSV}

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

# The 15 adult GBD age buckets the dietary RR curves span (>= 25 y).
ADULT_AGE_LABELS = [
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


def _ensure_raw_downloads() -> None:
    """Download the public UN WPP files into data/raw/ when missing.

    The GBD 2023 cause-specific death-rate CSV and theoretical minimum-risk life
    table require a (free) IHME account and cannot be auto-downloaded; a clear
    error points the developer at the acquisition guide. The GBD 2023
    relative-risk curves are fetched separately from the Burden-of-Proof tool
    (no login) by :func:`_fetch_bop_curves`.
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

    missing_manual = [
        path
        for path in (GBD_MORTALITY_CSV, GBD_REFERENCE_LIFE_TABLE_CSV)
        if not path.exists()
    ]
    if missing_manual:
        paths = "\n".join(f"  {path}" for path in missing_manual)
        raise FileNotFoundError(
            "Missing IHME GBD raw input(s). These require a free IHME account; "
            "see docs/data_sources.md for download instructions:\n" + paths
        )


# --------------------------------------------------------------------------
# Relative risks
# --------------------------------------------------------------------------


_RR_CURVE_COLS = [
    "risk_factor",
    "cause",
    "exposure_g_per_day",
    "rr_mean",
    "rr_low",
    "rr_high",
]


def _bop_get(path: str, **params) -> object:
    """GET one Burden-of-Proof JSON endpoint with a browser User-Agent."""
    qs = urllib.parse.urlencode(params)
    url = f"{BOP_API_BASE}/{path}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(  # noqa: S310 (trusted IHME host)
        url,
        headers={
            "User-Agent": BOP_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://vizhub.healthdata.org/burden-of-proof/",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        return json.load(resp)


def _fetch_bop_curves() -> pd.DataFrame:
    """Fetch the all-ages GBD 2023 Burden-of-Proof RR curve for every needed pair.

    Returns one row per curve point in the GBD intake basis::

        risk_factor, cause, exposure_g_per_day, rr_mean, rr_low, rr_high

    Every ``(risk, cause)`` in :data:`RISK_CAUSE_MAP` must be offered by the
    tool (red_meat is included so its exposure grid is available for the
    literature override). The result is cached to ``BOP_CURVES_CSV``.
    """
    manifest = _bop_get("metadata/risk_cause")  # {rei_id: [cause_id, ...]}
    rows: list[dict] = []
    for risk, causes in RISK_CAUSE_MAP.items():
        rei = GBD_REI_ID[risk]
        available = set(manifest.get(str(rei), []))
        for cause in causes:
            cid = GBD_CAUSE_ID[cause]
            if cid not in available:
                raise ValueError(
                    f"{risk}->{cause} (rei {rei}, cause {cid}) not offered by the "
                    "Burden-of-Proof tool; check GBD_REI_ID / RISK_CAUSE_MAP."
                )
            meta = _bop_get("risk_cause_metadata", risk=rei, cause=cid)
            if meta.get("risk_unit") != "g/day":
                raise ValueError(
                    f"{risk}->{cause}: unexpected BoP exposure unit "
                    f"{meta.get('risk_unit')!r} (only 'g/day' is supported)"
                )
            curve = _bop_get("output_data", risk=rei, cause=cid)
            xs = [float(p["risk"]) for p in curve]
            if xs != sorted(xs):
                raise ValueError(f"{risk}->{cause}: BoP exposure grid not ascending")
            for p in curve:
                rr_mean = float(p["linear_cause"])
                rr_low = float(p["linear_cause_lower"])
                rr_high = float(p["linear_cause_upper"])
                if not (rr_low > 0 and rr_mean > 0 and rr_high > 0):
                    raise ValueError(
                        f"{risk}->{cause}: non-positive RR at x={p['risk']}"
                    )
                rows.append(
                    {
                        "risk_factor": risk,
                        "cause": cause,
                        "exposure_g_per_day": float(p["risk"]),
                        "rr_mean": rr_mean,
                        "rr_low": rr_low,
                        "rr_high": rr_high,
                    }
                )
            print(f"  BoP {risk} -> {cause}: {len(curve)} points")

    return (
        pd.DataFrame(rows, columns=_RR_CURVE_COLS)
        .sort_values(["risk_factor", "cause", "exposure_g_per_day"])
        .reset_index(drop=True)
    )


def _load_bop_curves() -> pd.DataFrame:
    """Return complete cached BoP curves, refreshing a stale/incomplete cache."""
    expected_pairs = {
        (risk, cause) for risk, causes in RISK_CAUSE_MAP.items() for cause in causes
    }
    if BOP_CURVES_CSV.exists():
        cached = pd.read_csv(BOP_CURVES_CSV)
        cached_pairs = set(
            cached[["risk_factor", "cause"]].itertuples(index=False, name=None)
        )
        if cached_pairs == expected_pairs:
            return cached
        missing = sorted(expected_pairs - cached_pairs)
        extra = sorted(cached_pairs - expected_pairs)
        print(
            "Refreshing incomplete/stale Burden-of-Proof cache "
            f"(missing={missing}, extra={extra}) ..."
        )
    print("Fetching GBD 2023 Burden-of-Proof relative-risk curves ...")
    try:
        df = _fetch_bop_curves()
    except urllib.error.HTTPError as exc:  # pragma: no cover - network dependent
        raise RuntimeError(
            "Burden-of-Proof fetch failed "
            f"({exc.code} {exc.reason}); cloud IPs may be blocked by the edge "
            "bot-check. Run this once from a normal machine — the curves cache "
            f"to {BOP_CURVES_CSV}."
        ) from exc
    df.to_csv(BOP_CURVES_CSV, index=False)
    return df


def _parse_per_unit(per_unit: str) -> float:
    """Parse a per-unit string like '100 g/day' into the numeric g/day value."""
    parts = str(per_unit).strip().split()
    if len(parts) < 2:
        raise ValueError(f"Cannot parse per_unit: '{per_unit}'")
    return float(parts[0])


def _override_all_ages(risk: str, causes: list[str], grid: list[float]) -> pd.DataFrame:
    """Build all-ages log-linear curves ``RR(x) = rr^(x / per_unit)`` from a CSV.

    Used for risks in :data:`ALTERNATIVE_RR` (red meat). The exposure *grid* is
    the basis-converted BoP grid so the model basis is preserved; the central/CI
    multipliers come from the literature meta-analyses in the curated CSV.
    """
    alt = pd.read_csv(ALTERNATIVE_RR[risk])
    rows: list[dict] = []
    found: set[str] = set()
    for _, r in alt.iterrows():
        cause = str(r["outcome"])
        if cause not in causes:
            continue
        found.add(cause)
        per_unit = _parse_per_unit(r["per_unit"])
        central, low, high = (
            float(r["rr_central"]),
            float(r["rr_lower_95ci"]),
            float(r["rr_upper_95ci"]),
        )
        for x in grid:
            ratio = x / per_unit
            rows.append(
                {
                    "risk_factor": risk,
                    "cause": cause,
                    "exposure_g_per_day": x,
                    "rr_mean": central**ratio,
                    "rr_low": low**ratio,
                    "rr_high": high**ratio,
                }
            )
    missing = set(causes) - found
    if missing:
        raise ValueError(
            f"Override RR CSV for '{risk}' missing causes: {sorted(missing)}"
        )
    return pd.DataFrame(rows, columns=_RR_CURVE_COLS)


def _ensure_knot(g: pd.DataFrame, x0: float) -> pd.DataFrame:
    """Insert exposure knot x0 (log-linear interpolation) if not already present."""
    xs = g["exposure_g_per_day"].to_numpy(float)
    if np.any(np.isclose(xs, x0)):
        return g
    row = {
        "risk_factor": g["risk_factor"].iloc[0],
        "cause": g["cause"].iloc[0],
        "exposure_g_per_day": float(x0),
    }
    for col in ("rr_mean", "rr_low", "rr_high"):
        row[col] = float(np.exp(np.interp(x0, xs, np.log(g[col].to_numpy(float)))))
    return (
        pd.concat([g, pd.DataFrame([row])], ignore_index=True)
        .sort_values("exposure_g_per_day")
        .reset_index(drop=True)
    )


def _clip_at_tmrel(g: pd.DataFrame, tmrel: float, risk_type: str) -> pd.DataFrame:
    """Truncate the curve at the TMREL so the flat plateau lies on its benefit side.

    Protective risks: keep exposures <= TMREL (the model clamps flat beyond the
    data range, giving no further benefit above the TMREL). Harmful risks: keep
    exposures >= TMREL. The model then evaluates PAF relative to the baseline
    diet; the TMREL only shapes where each curve plateaus.
    """
    g = g.sort_values("exposure_g_per_day").reset_index(drop=True)
    xs = g["exposure_g_per_day"].to_numpy(float)
    risk, cause = g["risk_factor"].iloc[0], g["cause"].iloc[0]

    if risk_type == "protective":
        if tmrel <= xs[0]:
            raise ValueError(
                f"Protective TMREL {tmrel} <= min exposure for {risk}->{cause}"
            )
        if tmrel < xs[-1]:
            g = _ensure_knot(g, tmrel)
            g = g[g["exposure_g_per_day"] <= tmrel + 1e-9]
    elif risk_type == "harmful":
        if tmrel >= xs[-1]:
            raise ValueError(
                f"Harmful TMREL {tmrel} >= max exposure for {risk}->{cause}"
            )
        if tmrel > xs[0]:
            g = _ensure_knot(g, tmrel)
            g = g[g["exposure_g_per_day"] >= tmrel - 1e-9]
    else:
        raise ValueError(f"Unknown risk_type {risk_type!r} for {risk}")
    return g.reset_index(drop=True)


# Max exposure knots kept per curve before age expansion. The model reads RR by
# log-linear interpolation, so a smooth monotone BoP curve is reproduced to a few
# tenths of a percent by ~40 evenly-spaced knots (and the red-meat log-linear
# override is reproduced exactly by any knot subset). Keeps the bundled CSV small.
MAX_RR_KNOTS = 40


def _thin(g: pd.DataFrame, n: int) -> pd.DataFrame:
    """Subsample an exposure-sorted curve to <= n knots, keeping both endpoints."""
    g = g.sort_values("exposure_g_per_day").reset_index(drop=True)
    if len(g) <= n:
        return g
    idx = sorted(set(np.linspace(0, len(g) - 1, n).round().astype(int)))
    return g.iloc[idx].reset_index(drop=True)


def _age_expand(
    g: pd.DataFrame, beta_lookup: dict[tuple[str, str, str], float]
) -> pd.DataFrame:
    """Expand an all-ages curve to 15 ages: RR_age = exp(beta(age) * log RR)."""
    risk, cause = g["risk_factor"].iloc[0], g["cause"].iloc[0]
    x = g["exposure_g_per_day"].to_numpy(float)
    log_mean = np.log(g["rr_mean"].to_numpy(float))
    log_low = np.log(g["rr_low"].to_numpy(float))
    log_high = np.log(g["rr_high"].to_numpy(float))

    frames = []
    for age in ADULT_AGE_LABELS:
        beta = beta_lookup[(risk, cause, age)]
        frames.append(
            pd.DataFrame(
                {
                    "risk_factor": risk,
                    "cause": cause,
                    "age": age,
                    "exposure_g_per_day": x,
                    "rr_mean": np.exp(beta * log_mean),
                    "rr_low": np.exp(beta * log_low),
                    "rr_high": np.exp(beta * log_high),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def build_relative_risks() -> pd.DataFrame:
    """Build the model-basis dose-response table from GBD 2023 Burden of Proof.

    For each ``(risk_factor, cause)``: take the all-ages BoP curve (or, for
    red meat, the literature log-linear override on the BoP exposure grid),
    convert the exposure axis to the model basis, clip at the curated TMREL,
    then expand to the 15 adult age groups via the curated multiplicative
    log-RR age-attenuation table. nuts_seeds->T2DM is absent in GBD 2023.
    """
    bop = _load_bop_curves()
    bop["exposure_g_per_day"] = bop["exposure_g_per_day"] * bop["risk_factor"].map(
        lambda r: RR_BASIS_FACTOR.get(r, 1.0)
    )

    beta_df = pd.read_csv(RR_AGE_ATTENUATION_CSV)
    beta_lookup = {
        (r, c, a): float(b)
        for r, c, a, b in beta_df[["risk_factor", "cause", "age", "beta"]].itertuples(
            index=False
        )
    }

    tmrel_df = pd.read_csv(RR_TMREL_CSV).set_index("risk_factor")
    tmrel_model: dict[str, float] = {}
    risk_type: dict[str, str] = {}
    for risk in RISK_CAUSE_MAP:
        row = tmrel_df.loc[risk]
        f = RR_BASIS_FACTOR.get(risk, 1.0)
        tmrel_model[risk] = (
            0.5 * (float(row["tmrel_low"]) + float(row["tmrel_high"])) * f
        )
        risk_type[risk] = str(row["risk_type"])

    out_frames: list[pd.DataFrame] = []
    for risk, causes in RISK_CAUSE_MAP.items():
        if risk in ALTERNATIVE_RR:
            grid = sorted(
                bop.loc[bop["risk_factor"] == risk, "exposure_g_per_day"].unique()
            )
            if not grid:
                raise ValueError(f"No BoP exposure grid for override risk '{risk}'")
            all_ages = _override_all_ages(risk, causes, grid)
        else:
            all_ages = bop[(bop["risk_factor"] == risk) & (bop["cause"].isin(causes))][
                _RR_CURVE_COLS
            ]
        for cause in causes:
            g = all_ages[all_ages["cause"] == cause]
            if g.empty:
                raise ValueError(f"Missing curve for {risk}->{cause}")
            g = _clip_at_tmrel(g, tmrel_model[risk], risk_type[risk])
            g = _thin(g, MAX_RR_KNOTS)
            out_frames.append(_age_expand(g, beta_lookup))

    return (
        pd.concat(out_frames, ignore_index=True)
        .sort_values(["risk_factor", "cause", "age", "exposure_g_per_day"])
        .reset_index(drop=True)
    )


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


def build_local_life_table(countries: set[str]) -> pd.DataFrame:
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
# GBD theoretical minimum-risk reference life table
# --------------------------------------------------------------------------


def build_standard_life_table() -> pd.DataFrame:
    """Adapt the GBD 2023 TMRLT to the model's abridged age buckets.

    The upstream table gives remaining life expectancy at exact age boundaries
    through age 110. The model's final band is 95+, so its value is the
    upstream life expectancy at the lower boundary, age 95, consistently with
    the other abridged bands.
    """
    raw = pd.read_csv(GBD_REFERENCE_LIFE_TABLE_CSV)
    required_columns = {"Age", "Life Expectancy"}
    missing_columns = required_columns - set(raw.columns)
    if missing_columns:
        raise ValueError(
            f"{GBD_REFERENCE_LIFE_TABLE_CSV.name} is missing columns: "
            f"{sorted(missing_columns)}"
        )

    table = raw[["Age", "Life Expectancy"]].copy()
    table["Age"] = pd.to_numeric(table["Age"], errors="raise")
    table["Life Expectancy"] = pd.to_numeric(table["Life Expectancy"], errors="raise")
    if table["Age"].duplicated().any():
        duplicates = sorted(table.loc[table["Age"].duplicated(), "Age"].tolist())
        raise ValueError(
            f"{GBD_REFERENCE_LIFE_TABLE_CSV.name} has duplicate ages: {duplicates}"
        )

    age_starts = [0, 1, *range(5, 100, 5)]
    indexed = table.set_index("Age")["Life Expectancy"]
    missing_ages = [age for age in age_starts if age not in indexed.index]
    if missing_ages:
        raise ValueError(
            f"{GBD_REFERENCE_LIFE_TABLE_CSV.name} is missing required age "
            f"boundaries: {missing_ages}"
        )

    ex = indexed.loc[age_starts].to_numpy(dtype=float)
    if not np.isfinite(ex).all() or (ex <= 0).any():
        raise ValueError(
            f"{GBD_REFERENCE_LIFE_TABLE_CSV.name} has invalid life expectancy values"
        )
    return pd.DataFrame({"age": AGE_BUCKETS, "ex": ex})


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
    print("Building standard_life_table.csv ...")
    standard_life_table = build_standard_life_table()

    # The baseline diet (a separate, bundled dataset) defines the country
    # universe; every diet country must have complete burden inputs.
    baseline_intake = pd.read_csv(OUT_DIR / "baseline_intake.csv")
    diet_countries = set(baseline_intake["country"])

    print("Building local_life_table.csv ...")
    local_life_table = build_local_life_table(diet_countries)

    complete = (
        set(mort["country"]) & set(pop["country"]) & set(local_life_table["country"])
    )
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
    local_life_table = local_life_table[local_life_table["country"].isin(keep)]
    print(f"Countries with complete data: {len(keep)}")

    rr.to_csv(OUT_DIR / "relative_risks.csv", index=False)
    mort.to_csv(OUT_DIR / "mortality.csv", index=False)
    pop.to_csv(OUT_DIR / "population.csv", index=False)
    local_life_table.to_csv(OUT_DIR / "local_life_table.csv", index=False)
    standard_life_table.to_csv(OUT_DIR / "standard_life_table.csv", index=False)

    print("\nWrote:")
    for name, df in [
        ("relative_risks", rr),
        ("mortality", mort),
        ("population", pop),
        ("local_life_table", local_life_table),
        ("standard_life_table", standard_life_table),
    ]:
        print(f"  {name}.csv: {len(df)} rows")


if __name__ == "__main__":
    main()
