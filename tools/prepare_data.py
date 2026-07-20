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
- ``mortality.csv``       WHO GHE 2021 cause-specific death rates (year 2020):
                          country, sex, cause, age, death_rate_per_1000
- ``population.csv``      UN WPP population by age/sex:
                          age, sex, country, population
- ``local_life_table.csv`` UN WPP abridged life table:
                          country, sex, age, lx, ex
- ``standard_life_table.csv`` GBD 2023 theoretical minimum-risk life
                          expectancy: age, ex

Raw inputs live under ``data/raw/`` (see ``docs/development/data_build.md`` for how to
obtain each one). The WHO mortality data, two UN WPP files, and GBD 2023
Burden-of-Proof RR curves are fetched automatically. The relative-risk age
structure and TMRELs come from curated tables under
``tools/reference/`` (see ``tools/generate_rr_age_attenuation.py``).

The direct exposure and calorie baselines are separate datasets and are **not**
built here. This module is an internal stage invoked by
``tools/build_data.py``; see ``docs/development/data_build.md`` for the workflow.
"""

from __future__ import annotations

from pathlib import Path
import re
import time
from typing import Literal, overload
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from tools.source_schemas import (
    BOP_CURVE_ADAPTER,
    BOP_CURVE_METADATA_ADAPTER,
    BOP_RISK_CAUSE_MANIFEST_ADAPTER,
    WHO_GHE_PAGE_ADAPTER,
    BopCurveMetadata,
    BopCurvePoint,
    WhoGhePage,
    WhoGheRow,
    validate_json_response,
)

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
REFERENCE_DIR = Path(__file__).resolve().parent / "reference"
OUT_DIR = ROOT / "src" / "mealhealth" / "data"

REFERENCE_YEAR = 2020

# Raw inputs (placed under data/raw/; see docs/development/data_build.md).
WHO_GHE_MORTALITY_CSV = RAW_DIR / "WHO_GHE_2021_mortality_2020.csv"
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

# WHO Global Health Estimates 2021 OData endpoint. The selected 2020 rows are
# public and require no account. One request is made per cause and sex so the
# API's ``$top`` cap can never silently truncate the result.
WHO_GHE_API_URL = "https://xmart-api-public.who.int/DEX_CMS/GHE_FULL"
WHO_GHE_SELECT_COLUMNS = (
    "DIM_COUNTRY_CODE",
    "DIM_YEAR_CODE",
    "DIM_AGEGROUP_CODE",
    "DIM_SEX_CODE",
    "DIM_GHECAUSE_CODE",
    "DIM_GHECAUSE_TITLE",
    "ATTR_POPULATION_NUMERIC",
    "VAL_DTHS_RATE100K_NUMERIC",
    "VAL_DTHS_COUNT_NUMERIC",
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

# Conversion of RR-curve axes from their native GBD/literature basis to the
# model input basis. Processed meat is already an as-eaten product basis and
# therefore has no cooked/raw conversion; only legumes and fresh red meat are
# converted here.
MEAT_COOKED_TO_FRESH = 1.43
LEGUMES_COOKED_TO_DRY = 0.40

RR_BASIS_FACTOR: dict[str, float] = {
    "legumes": LEGUMES_COOKED_TO_DRY,
    "red_meat": MEAT_COOKED_TO_FRESH,
    "processed_meat": 1.0,
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


def ensure_raw_downloads() -> None:
    """Download public WHO GHE and UN WPP files when missing.

    The GBD theoretical-minimum-risk life table still requires a free IHME
    account and is validated by its builder. Relative-risk curves are fetched
    separately from the public Burden-of-Proof tool.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if not WHO_GHE_MORTALITY_CSV.exists():
        print("Downloading 2020 cause-specific mortality from WHO GHE ...")
        retrieve_who_ghe_mortality().to_csv(WHO_GHE_MORTALITY_CSV, index=False)
    for path, url in (
        (WPP_POPULATION_GZ, WPP_POPULATION_URL),
        (WPP_LIFE_TABLE_GZ, WPP_LIFE_TABLE_URL),
    ):
        if path.exists():
            continue
        print(f"Downloading {path.name} from UN WPP ...")
        urllib.request.urlretrieve(url, path)  # noqa: S310 (trusted UN URL)


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


@overload
def _bop_get(
    path: Literal["metadata/risk_cause"], **params: str | int
) -> dict[str, list[int]]: ...


@overload
def _bop_get(
    path: Literal["risk_cause_metadata"], **params: str | int
) -> BopCurveMetadata: ...


@overload
def _bop_get(
    path: Literal["output_data"], **params: str | int
) -> list[BopCurvePoint]: ...


def _bop_get(
    path: str, **params: str | int
) -> dict[str, list[int]] | BopCurveMetadata | list[BopCurvePoint]:
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
        payload = resp.read()
    source = f"IHME Burden-of-Proof {path}"
    if path == "metadata/risk_cause":
        return validate_json_response(
            payload, BOP_RISK_CAUSE_MANIFEST_ADAPTER, source=source
        )
    if path == "risk_cause_metadata":
        return validate_json_response(
            payload, BOP_CURVE_METADATA_ADAPTER, source=source
        )
    if path == "output_data":
        return validate_json_response(payload, BOP_CURVE_ADAPTER, source=source)
    raise ValueError(f"Unsupported Burden-of-Proof endpoint: {path}")


def _fetch_bop_curves() -> pd.DataFrame:
    """Fetch the all-ages GBD 2023 Burden-of-Proof RR curve for every needed pair.

    Returns one row per curve point in the GBD intake basis::

        risk_factor, cause, exposure_g_per_day, rr_mean, rr_low, rr_high

    Every ``(risk, cause)`` in :data:`RISK_CAUSE_MAP` must be offered by the
    tool (red_meat is included so its exposure grid is available for the
    literature override). The result is cached to ``BOP_CURVES_CSV``.
    """
    manifest = _bop_get("metadata/risk_cause")  # {rei_id: [cause_id, ...]}
    rows: list[dict[str, object]] = []
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
            if meta["risk_unit"] != "g/day":
                raise ValueError(
                    f"{risk}->{cause}: unexpected BoP exposure unit "
                    f"{meta['risk_unit']!r} (only 'g/day' is supported)"
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
    rows: list[dict[str, object]] = []
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
        if not isinstance(row, pd.Series):
            raise ValueError(f"Duplicate TMREL rows for risk {risk!r}")
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
# Mortality (WHO Global Health Estimates 2021, reference year 2020)
# --------------------------------------------------------------------------

# WHO GHE identifiers. Haemorrhagic stroke and chronic kidney disease are
# intentionally aggregated because WHO does not expose the finer IHME cause
# taxonomy. All component causes in each aggregate use the same mealhealth RR
# curve, so summing their baseline rates preserves the burden calculation.
WHO_GHE_CAUSE_MAP = {
    640: "StomachCancer",
    650: "CRC",
    800: "T2DM",
    1130: "CHD",
    1141: "Stroke",
    1142: "HaemorrhagicStroke",
    1272: "CKD",
    1273: "CKD",
}
WHO_GHE_CAUSE_TITLES = {
    640: "Stomach cancer",
    650: "Colon and rectum cancers",
    800: "Diabetes mellitus",
    1130: "Ischaemic heart disease",
    1141: "Ischaemic stroke",
    1142: "Haemorrhagic stroke",
    1272: "Chronic kidney disease due to diabetes",
    1273: "Other chronic kidney disease",
}

WHO_GHE_AGE_MAP = {
    "Y0T1": "<1",
    "Y1T4": "1-4",
    **{f"Y{start}T{start + 4}": f"{start}-{start + 4}" for start in range(5, 85, 5)},
}
WHO_GHE_OPEN_AGE = "YGE_85"
WHO_GHE_OPEN_AGE_TARGETS = ("85-89", "90-94", "95+")

# Territories/dependencies without separate WHO Member State estimates.
MORTALITY_COUNTRY_PROXIES = {
    "ASM": "WSM",  # American Samoa -> Samoa
    "GUF": "FRA",  # French Guiana -> France
    "PRI": "USA",  # Puerto Rico -> USA
    "PSE": "JOR",  # State of Palestine -> Jordan
    "TWN": "KOR",  # Taiwan -> Republic of Korea
}


def _who_ghe_get(params: dict[str, str | int]) -> WhoGhePage:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(  # noqa: S310 (trusted WHO host)
        f"{WHO_GHE_API_URL}?{query}",
        headers={"Accept": "application/json", "User-Agent": "mealhealth-data/1"},
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=120
            ) as response:
                return validate_json_response(
                    response.read(), WHO_GHE_PAGE_ADAPTER, source="WHO GHE OData"
                )
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 4:
                raise
        except urllib.error.URLError:
            if attempt == 4:
                raise
        time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def retrieve_who_ghe_mortality() -> pd.DataFrame:
    """Retrieve complete 2020 age/sex mortality rows for model causes."""

    rows: list[WhoGheRow] = []
    for cause_id in WHO_GHE_CAUSE_MAP:
        for source_sex in ("MALE", "FEMALE"):
            params: dict[str, str | int] = {
                "$filter": (
                    f"DIM_YEAR_CODE eq {REFERENCE_YEAR} and "
                    f"DIM_SEX_CODE eq '{source_sex}' and "
                    f"DIM_GHECAUSE_CODE eq {cause_id}"
                ),
                "$select": ",".join(WHO_GHE_SELECT_COLUMNS),
                "$top": 10000,
            }
            payload = _who_ghe_get(params)
            page = payload.value
            if not page:
                raise ValueError(
                    f"WHO GHE returned no {source_sex} rows for cause {cause_id}"
                )
            if len(page) >= int(params["$top"]) or payload.next_link:
                raise ValueError(
                    "WHO GHE query may be truncated; reduce the query dimensions"
                )
            rows.extend(page)
    return pd.DataFrame(rows, columns=WHO_GHE_SELECT_COLUMNS)


def build_mortality(
    raw_path: Path = WHO_GHE_MORTALITY_CSV,
) -> pd.DataFrame:
    """Build WHO GHE sex-specific death rates per 1,000 person-years."""

    if not raw_path.exists():
        raise FileNotFoundError(f"Missing WHO GHE mortality cache:\n  {raw_path}")
    frame = pd.read_csv(raw_path)
    required = set(WHO_GHE_SELECT_COLUMNS)
    missing_columns = required - set(frame.columns)
    if missing_columns:
        raise ValueError(f"WHO GHE data missing columns: {sorted(missing_columns)}")

    frame["DIM_YEAR_CODE"] = pd.to_numeric(frame["DIM_YEAR_CODE"], errors="coerce")
    frame["DIM_GHECAUSE_CODE"] = pd.to_numeric(
        frame["DIM_GHECAUSE_CODE"], errors="coerce"
    )
    if set(frame["DIM_YEAR_CODE"]) != {REFERENCE_YEAR}:
        raise ValueError("WHO GHE mortality cache has an unexpected reference year")
    if set(frame["DIM_SEX_CODE"]) != {"MALE", "FEMALE"}:
        raise ValueError("WHO GHE mortality cache must contain male and female rows")
    if set(frame["DIM_GHECAUSE_CODE"]) != set(WHO_GHE_CAUSE_MAP):
        raise ValueError("WHO GHE mortality cache has unexpected cause coverage")
    cause_titles = set(
        frame[["DIM_GHECAUSE_CODE", "DIM_GHECAUSE_TITLE"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    if cause_titles != set(WHO_GHE_CAUSE_TITLES.items()):
        raise ValueError("WHO GHE mortality cache has unexpected cause titles")
    required_ages = set(WHO_GHE_AGE_MAP) | {WHO_GHE_OPEN_AGE}
    if not required_ages <= set(frame["DIM_AGEGROUP_CODE"]):
        raise ValueError("WHO GHE mortality cache has incomplete age coverage")

    source_key = [
        "DIM_COUNTRY_CODE",
        "DIM_SEX_CODE",
        "DIM_GHECAUSE_CODE",
        "DIM_AGEGROUP_CODE",
    ]
    if frame.duplicated(source_key).any():
        raise ValueError("WHO GHE mortality cache has duplicate cells")

    frame = frame[frame["DIM_AGEGROUP_CODE"].isin(required_ages)].copy()
    rates = pd.to_numeric(frame["VAL_DTHS_RATE100K_NUMERIC"], errors="coerce")
    if not np.isfinite(rates).all() or (rates < 0).any():
        raise ValueError("WHO GHE mortality rates must be finite and non-negative")
    frame["death_rate_per_1000"] = rates / 100.0
    frame["country"] = frame["DIM_COUNTRY_CODE"].astype(str)
    frame["sex"] = frame["DIM_SEX_CODE"].str.lower()
    frame["cause"] = frame["DIM_GHECAUSE_CODE"].map(WHO_GHE_CAUSE_MAP)
    frame["age"] = frame["DIM_AGEGROUP_CODE"].map(WHO_GHE_AGE_MAP)

    closed = frame[frame["age"].notna()].copy()
    open_age = frame[frame["DIM_AGEGROUP_CODE"] == WHO_GHE_OPEN_AGE]
    expanded = []
    for age in WHO_GHE_OPEN_AGE_TARGETS:
        part = open_age.copy()
        part["age"] = age
        expanded.append(part)
    frame = pd.concat([closed, *expanded], ignore_index=True)

    # The two chronic-kidney rows are additive components of one model cause.
    out = frame.groupby(["country", "sex", "cause", "age"], as_index=False)[
        ["death_rate_per_1000"]
    ].sum()
    out["source_country"] = out["country"]

    source_countries = sorted(out["country"].unique())
    model_causes = tuple(dict.fromkeys(WHO_GHE_CAUSE_MAP.values()))
    expected = pd.MultiIndex.from_product(
        [source_countries, ("male", "female"), model_causes, AGE_BUCKETS],
        names=["country", "sex", "cause", "age"],
    )
    actual = pd.MultiIndex.from_frame(out[["country", "sex", "cause", "age"]])
    missing = expected.difference(actual)
    if len(missing):
        raise ValueError(
            "WHO GHE mortality is missing source strata; "
            f"first entries: {list(missing[:10])}"
        )

    proxy_rows = []
    for target, proxy in MORTALITY_COUNTRY_PROXIES.items():
        rows = out[out["country"] == proxy].copy()
        if rows.empty:
            raise ValueError(f"WHO GHE mortality proxy source {proxy} is unavailable")
        rows["country"] = target
        proxy_rows.append(rows)
    out = pd.concat([out, *proxy_rows], ignore_index=True)
    out = out[
        [
            "country",
            "sex",
            "cause",
            "age",
            "source_country",
            "death_rate_per_1000",
        ]
    ]
    out = out.sort_values(["country", "sex", "cause", "age"]).reset_index(drop=True)
    return out


# --------------------------------------------------------------------------
# Population (UN WPP)
# --------------------------------------------------------------------------


def build_population() -> pd.DataFrame:
    """Per-country/sex population by age bucket (+ ``all-a``), persons, 2020.

    The WPP "Population by 5-year age group" file reports a combined ``0-4``
    band, so each sex's under-5 band is
    disaggregated into ``<1`` (20%) and ``1-4`` (80%) and the open-ended
    ``95-99`` / ``100+`` bands are merged into ``95+``.
    """
    df = pd.read_csv(WPP_POPULATION_GZ, compression="gzip", low_memory=False)
    df = df[df["Variant"].astype(str).str.lower() == "medium"]
    df = df[pd.to_numeric(df["Time"], errors="coerce") == REFERENCE_YEAR]
    df = df[df["ISO3_code"].notna()].copy()
    df["ISO3_code"] = df["ISO3_code"].astype(str).str.upper()
    for column in ("PopMale", "PopFemale"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["PopMale", "PopFemale"])
    df["AgeGrpStart"] = pd.to_numeric(df["AgeGrpStart"], errors="coerce")
    df["AgeGrpSpan"] = pd.to_numeric(df["AgeGrpSpan"], errors="coerce")

    records: list[dict[str, object]] = []
    for iso3, grp in df.groupby("ISO3_code"):
        for sex, population_column in (("male", "PopMale"), ("female", "PopFemale")):
            buckets: dict[str, float] = {}
            for _, row in grp.iterrows():
                bucket = _wpp_age_bucket(row["AgeGrpStart"], row["AgeGrpSpan"])
                if bucket is None:
                    continue
                buckets[bucket] = (
                    buckets.get(bucket, 0.0) + float(row[population_column]) * 1000.0
                )

            # Disaggregate a combined 0-4 band into <1 / 1-4 where granular
            # bands are absent (the 5-year-group file reports only 0-4).
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
                continue  # dropped later by the country intersection
            for age in AGE_BUCKETS:
                records.append(
                    {
                        "age": age,
                        "sex": sex,
                        "country": iso3,
                        "population": buckets[age],
                    }
                )
            records.append(
                {
                    "age": "all-a",
                    "sex": sex,
                    "country": iso3,
                    "population": sum(buckets[a] for a in AGE_BUCKETS),
                }
            )

    out = pd.DataFrame(records)
    out["age"] = pd.Categorical(
        out["age"], categories=[*AGE_BUCKETS, "all-a"], ordered=True
    )
    return out.sort_values(["country", "sex", "age"]).reset_index(drop=True)


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
    """Per-country/sex abridged life table (lx survivors and remaining ex).

    Falls back to the World life table for countries WPP lacks individually.
    The WPP abridged file starts in 2024, so the nearest year is used.
    """
    raw = pd.read_csv(WPP_LIFE_TABLE_GZ, low_memory=False)
    raw = raw[raw["Variant"].astype(str).str.lower() == "medium"].copy()
    raw["sex"] = raw["Sex"].astype(str).str.lower()
    raw = raw[raw["sex"].isin(["male", "female"])].copy()
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

    def _table_for(
        df: pd.DataFrame, country: str, sex: str
    ) -> list[dict[str, object]] | None:
        seen: set[str] = set()
        recs: list[dict[str, object]] = []
        for _, r in df.iterrows():
            b = str(r["bucket"])
            if b in seen:
                continue
            try:
                lx, ex = float(r["lx"]), float(r["ex"])
            except (TypeError, ValueError):
                continue
            seen.add(b)
            recs.append({"country": country, "sex": sex, "age": b, "lx": lx, "ex": ex})
        if not all(b in seen for b in AGE_BUCKETS):
            return None
        return recs

    world = raw[raw["Location"].astype(str) == "World"]
    world_recs = {
        sex: _table_for(world[world["sex"] == sex], "WORLD", sex)
        for sex in ("male", "female")
    }
    if any(records is None for records in world_recs.values()):
        raise RuntimeError("Could not build sex-specific World life table fallback")

    out_rows: list[dict[str, object]] = []
    by_iso_sex = {
        (str(country), str(sex)): frame
        for (country, sex), frame in raw.groupby(["ISO3_code", "sex"])
    }
    n_fallback = 0
    for c in sorted(countries):
        for sex in ("male", "female"):
            key = (c, sex)
            recs = _table_for(by_iso_sex[key], c, sex) if key in by_iso_sex else None
            if recs is None:
                recs = [{**r, "country": c} for r in world_recs[sex] or []]
                n_fallback += 1
            out_rows.extend(recs)
    print(
        f"  life table: {2 * len(countries) - n_fallback} country-sex tables, "
        f"{n_fallback} World fallbacks"
    )

    out = pd.DataFrame(out_rows)
    out["age"] = pd.Categorical(out["age"], categories=AGE_BUCKETS, ordered=True)
    return out.sort_values(["country", "sex", "age"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# GBD theoretical minimum-risk reference life table
# --------------------------------------------------------------------------


def build_standard_life_table() -> pd.DataFrame:
    """Adapt the GBD 2023 TMRLT to the model's abridged age buckets."""
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


def build_and_write_health_data(
    *, output_dir: Path = OUT_DIR
) -> dict[str, pd.DataFrame]:
    """Build and write the health and demographic package data."""

    output_dir.mkdir(parents=True, exist_ok=True)

    print("Building relative_risks.csv ...")
    rr = build_relative_risks()
    print("Building mortality.csv ...")
    mort = build_mortality()
    print("Building population.csv ...")
    pop = build_population()
    print("Building standard_life_table.csv ...")
    standard_life_table = build_standard_life_table()

    # The direct exposure baseline defines the country universe; every target
    # country must have complete burden inputs.
    baseline_exposure = pd.read_csv(output_dir / "baseline_exposure.csv")
    diet_countries = set(baseline_exposure["country"])

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
            "data may be out of sync; refresh the baseline exposure table too."
        )

    keep = diet_countries
    mort = mort[mort["country"].isin(keep)]
    pop = pop[pop["country"].isin(keep)]
    local_life_table = local_life_table[local_life_table["country"].isin(keep)]
    print(f"Countries with complete data: {len(keep)}")

    outputs = {
        "relative_risks": rr,
        "mortality": mort,
        "population": pop,
        "local_life_table": local_life_table,
        "standard_life_table": standard_life_table,
    }
    for name, frame in outputs.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)

    print("\nWrote:")
    for name, frame in outputs.items():
        print(f"  {name}.csv: {len(frame)} rows")
    return outputs


def main() -> None:
    ensure_raw_downloads()
    build_and_write_health_data()


if __name__ == "__main__":
    main()
