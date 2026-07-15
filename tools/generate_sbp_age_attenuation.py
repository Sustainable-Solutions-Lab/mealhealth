#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate the curated SBP relative-risk age attenuation table.

The public GBD 2023 Burden-of-Proof curves are all-age curves.  This one-off
developer tool derives their age shape from the GBD 2019 relative-risk workbook
and normalizes every outcome to the 60--64 reference age.  The resulting
dimensionless ratios are bundled as a transparent vintage bridge; the workbook
is not needed at package runtime.

Run from the repository root::

    python tools/generate_sbp_age_attenuation.py
"""

from __future__ import annotations

import math
from pathlib import Path
import re

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GBD2019_RR_XLSX = (
    ROOT / "data" / "raw" / "IHME_GBD_2019_RELATIVE_RISKS_Y2020M10D15.XLSX"
)
OUTPUT = Path(__file__).resolve().parent / "reference" / "sbp_age_attenuation.csv"
BUNDLED_OUTPUT = ROOT / "src" / "mealhealth" / "data" / "sbp_age_attenuation.csv"

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
REFERENCE_AGE = "60-64"

# The all-stroke BoP curve uses the ischemic-stroke age shape for this
# transparent prototype. WHO haemorrhagic stroke receives the same resulting
# sodium risk ratio, matching the selected all-stroke curve.
OUTCOME_ROWS = {
    "CHD": "Ischaemic heart disease",
    "Stroke": "Ischaemic stroke",
    "CKD": "Chronic kidney disease due to diabetes mellitus type 2",
}

_NUMBER = re.compile(r"[-+]?(?:\d+\.\d+|\d+)")


def _mean_rr(value: object) -> float:
    if isinstance(value, (int, float)) and not (
        isinstance(value, float) and math.isnan(value)
    ):
        return float(value)
    if not isinstance(value, str):
        raise ValueError(f"Could not parse RR cell {value!r}")
    matches = _NUMBER.findall(value)
    if not matches:
        raise ValueError(f"Could not parse RR cell {value!r}")
    return float(matches[0])


def build_age_attenuation(xlsx: Path = GBD2019_RR_XLSX) -> pd.DataFrame:
    """Return age-specific log-RR multipliers for the three SBP curves."""

    raw = pd.read_excel(xlsx, header=None)
    marker_rows = raw.index[raw[0] == "High systolic blood pressure"].tolist()
    if len(marker_rows) != 1:
        raise ValueError("Expected exactly one high-SBP block in the GBD workbook")
    start = marker_rows[0] + 1
    end_candidates = raw.index[
        (raw.index > start) & raw[0].notna() & raw[1].isna()
    ].tolist()
    end = end_candidates[0] if end_candidates else len(raw)
    block = raw.iloc[start:end]

    rows: list[dict[str, object]] = []
    for curve_cause, source_outcome in OUTCOME_ROWS.items():
        matches = block[block[0] == source_outcome]
        if len(matches) != 1 or str(matches.iloc[0, 1]).strip() != "10 mmHg":
            raise ValueError(f"Could not identify 10-mmHg row for {source_outcome}")
        source = matches.iloc[0]
        rr = {
            age: _mean_rr(source[column]) for column, age in ADULT_AGE_COLUMNS.items()
        }
        reference_log_rr = math.log(rr[REFERENCE_AGE])
        if reference_log_rr <= 0:
            raise ValueError(f"Invalid {REFERENCE_AGE} RR for {source_outcome}")
        for age in ADULT_AGE_COLUMNS.values():
            rows.append(
                {
                    "curve_cause": curve_cause,
                    "age": age,
                    "beta": math.log(rr[age]) / reference_log_rr,
                }
            )

    return pd.DataFrame(rows).sort_values(["curve_cause", "age"]).reset_index(drop=True)


def main() -> None:
    if not GBD2019_RR_XLSX.exists():
        raise FileNotFoundError(f"Missing {GBD2019_RR_XLSX}; see docs/data_sources.md.")
    result = build_age_attenuation()
    for output in (OUTPUT, BUNDLED_OUTPUT):
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
        print(f"Wrote {len(result)} rows to {output}")


if __name__ == "__main__":
    main()
