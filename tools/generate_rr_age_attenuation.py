#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate the curated dietary RR age-attenuation table (one-off dev tool).

The IHME GBD 2023 Burden-of-Proof tool only serves age-aggregated ("All Ages")
dietary relative-risk curves. GBD nonetheless applies age-specific RRs for
cardiovascular outcomes — the proportional effect attenuates with age — while
diabetes and colorectal cancer carry no age attenuation. We reconstruct that age
structure **once** from the GBD 2019 relative-risk workbook and freeze it into
``tools/reference/rr_age_attenuation.csv`` so the per-build pipeline
(``tools/prepare_data.py``) no longer depends on the GBD 2019 workbook.

Method
------
The log-RR age attenuation is multiplicative and essentially exposure-independent:

    log RR_age(x) ~= beta(age) * log RR_ref(x)

Per the GBD risk-factors capstone appendix, GBD assigns the estimated risk curve
to a *reference age group* — the median age-at-event, 60-64 years for the
cardiovascular age trend (the same trend is applied to dietary CVD outcomes) —
and derives age-specific RRs by attenuation relative to it. The Burden-of-Proof
"All Ages" curve is therefore the 60-64 reference-age curve. We mirror that
exactly: take the GBD 2019 age shape and normalize it to the 60-64 reference,

    beta(risk, cause, a) = log RR(a) / log RR(60-64)

so age-expanding the BoP curve reproduces it at 60-64, attenuates to older ages,
and amplifies to younger ages, as GBD does. T2DM and CRC carry no age
attenuation (their GBD 2019 curves are age-invariant, so beta = 1).

Provenance: the age *shape* is taken from the GBD 2019 RR appendix; the 60-64
reference age is GBD's documented choice. This is a derived result (a table of
dimensionless ratios), not a redistribution of GBD RR values.

Run once from the repository root with the dev environment::

    python tools/generate_rr_age_attenuation.py
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
import re
from typing import cast

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
GBD2019_RR_XLSX = (
    ROOT / "data" / "raw" / "IHME_GBD_2019_RELATIVE_RISKS_Y2020M10D15.XLSX"
)
OUTPUT = Path(__file__).resolve().parent / "reference" / "rr_age_attenuation.csv"

# IHME GBD relative-risk block names (XLSX column 0) -> model risk factor.
GBD_RISK_NAMES = {
    "Diet low in fruits": "fruits",
    "Diet low in vegetables": "vegetables",
    "Diet low in whole grains": "whole_grains",
    "Diet low in legumes": "legumes",
    "Diet low in nuts and seeds": "nuts_seeds",
    "Diet high in red meat": "red_meat",
    "Diet high in processed meat": "processed_meat",
    "Diet low in seafood omega-3 fatty acids": "omega3",
}

# IHME outcome name -> model cause (RR sheet uses "Diabetes mellitus type 2").
GBD_RR_CAUSE_MAP = {
    "Ischemic heart disease": "CHD",
    "Ischemic stroke": "Stroke",
    "Diabetes mellitus type 2": "T2DM",
    "Colon and rectum cancer": "CRC",
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

# (risk_factor -> causes) for which the BoP pipeline needs an age structure.
# red_meat keeps its literature override but still needs its causes' age shape.
NEEDED = {
    "fruits": ["CHD", "Stroke", "T2DM"],
    "vegetables": ["CHD", "Stroke"],
    "whole_grains": ["CHD", "Stroke", "T2DM", "CRC"],
    "legumes": ["CHD"],
    "nuts_seeds": ["CHD"],
    "red_meat": ["CHD", "Stroke", "T2DM", "CRC"],
    "processed_meat": ["CHD", "T2DM", "CRC"],
    "omega3": ["CHD"],
}

YOUNGEST_AGE = ADULT_AGE_LABELS[0]  # 25-29; numerically stable ratio denominator
REFERENCE_AGE = "60-64"  # GBD reference age group for the CVD age trend
_LOG_RR_EPS = 0.02  # ignore exposures where the reference log-RR is ~0 (unstable)
_NUM = re.compile(r"[-+]?(?:\d+\.\d+|\d+)")


def _parse_rr_cell(cell: object) -> float | None:
    """Parse '1.13 \\n (1 to 1.26)' -> mean RR (first number)."""
    if isinstance(cell, (int, float)) and not (
        isinstance(cell, float) and math.isnan(cell)
    ):
        return float(cell)
    if not isinstance(cell, str):
        return None
    nums = _NUM.findall(cell)
    return float(nums[0]) if nums else None


def parse_gbd2019_rr(xlsx: Path) -> pd.DataFrame:
    """Parse the GBD 2019 RR workbook into tidy mean-RR records (15 adult ages)."""
    raw = pd.read_excel(xlsx, header=None)
    diet_rows = [
        i
        for i, value in raw[0].items()
        if isinstance(i, int) and isinstance(value, str) and value.startswith("Diet")
    ]

    records: list[dict[str, object]] = []
    for k, start in enumerate(diet_rows):
        risk = GBD_RISK_NAMES.get(str(raw.at[start, 0]).strip())
        if risk is None:
            continue
        end = diet_rows[k + 1] if k + 1 < len(diet_rows) else len(raw)
        for _, row in raw.iloc[start + 1 : end].iterrows():
            outcome, exposure = row[0], row[1]
            if not isinstance(outcome, str) or not isinstance(exposure, str):
                continue
            if outcome not in GBD_RR_CAUSE_MAP:
                continue
            m = re.match(r"\s*([0-9.]+)\s*g/day", exposure)
            if not m:
                continue
            exp_g = float(m.group(1))
            for col, age in ADULT_AGE_COLUMNS.items():
                if col >= len(row):
                    continue
                rr = _parse_rr_cell(row[col])
                if rr is None:
                    continue
                records.append(
                    {
                        "risk_factor": risk,
                        "cause": GBD_RR_CAUSE_MAP[outcome],
                        "age": age,
                        "exposure_g_per_day": exp_g,
                        "rr_mean": rr,
                    }
                )
    return _fill_missing_ages(pd.DataFrame(records))


def _fill_missing_ages(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure every (risk, cause, exposure) triple has all 15 adult ages.

    Missing ages copy from the nearest younger age (then nearest older), so the
    log-RR shape ratios below are computed over a complete age grid.
    """
    rows: list[dict[str, object]] = []
    for key, grp in df.groupby(["risk_factor", "cause", "exposure_g_per_day"]):
        risk, cause, exp = cast(tuple[str, str, float], key)
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
                }
            )
    if rows:
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    return df


def _extract_shape(rr19: pd.DataFrame) -> dict[tuple[str, str, str], float]:
    """log-RR age shape, normalized to the youngest adult bucket (clamped [0, 1])."""
    shape: dict[tuple[str, str, str], float] = {}
    for key, g in rr19.groupby(["risk_factor", "cause"]):
        risk, cause = cast(tuple[str, str], key)
        piv = g.pivot_table(index="exposure_g_per_day", columns="age", values="rr_mean")
        missing = [a for a in ADULT_AGE_LABELS if a not in piv.columns]
        if missing:
            raise ValueError(f"GBD 2019 RR missing ages for {risk}->{cause}: {missing}")
        x = piv.index.values
        sel = x > 0
        log_young = np.log(piv[YOUNGEST_AGE].values[sel])
        stable = np.abs(log_young) >= _LOG_RR_EPS
        for age in ADULT_AGE_LABELS:
            ratios = np.log(piv[age].values[sel])[stable] / log_young[stable]
            val = 1.0 if ratios.size == 0 else float(np.median(ratios))
            shape[(risk, cause, age)] = max(0.0, min(1.0, val))
    return shape


def main() -> None:
    if not GBD2019_RR_XLSX.exists():
        raise FileNotFoundError(
            f"Missing {GBD2019_RR_XLSX} (the GBD 2019 RR workbook is the donor for "
            "the age structure; see docs/data_sources.md for how to obtain it)."
        )
    rr19 = parse_gbd2019_rr(GBD2019_RR_XLSX)
    shape = _extract_shape(rr19)

    rows = []
    logger.info(
        f"{'risk->cause':24} {'beta[25-29]':>11} {'beta[60-64]':>11} {'beta[95+]':>9}"
    )
    for risk, causes in NEEDED.items():
        for cause in causes:
            ref = shape.get((risk, cause, REFERENCE_AGE))
            if not ref or ref <= 0:
                raise ValueError(
                    f"No usable {REFERENCE_AGE} reference for {risk}->{cause}"
                )
            for age in ADULT_AGE_LABELS:
                rows.append(
                    {
                        "risk_factor": risk,
                        "cause": cause,
                        "age": age,
                        "beta": shape[(risk, cause, age)] / ref,
                    }
                )
            young = shape[(risk, cause, YOUNGEST_AGE)] / ref
            old = shape[(risk, cause, ADULT_AGE_LABELS[-1])] / ref
            logger.info(
                f"  {risk + '->' + cause:22} {young:11.2f} {1.0:11.2f} {old:9.2f}"
            )

    out = pd.DataFrame(rows).sort_values(["risk_factor", "cause", "age"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT, index=False)
    logger.info(f"\nwrote {len(out)} rows -> {OUTPUT}")


if __name__ == "__main__":
    main()
