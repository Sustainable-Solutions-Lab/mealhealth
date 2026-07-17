#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build the bundled GBD 2023 sodium and SBP BoP curve table.

The Burden-of-Proof API is public and requires no authenticated GBD download.
This builder validates the expected unit and evidence rating for every selected
curve before writing the compact all-age curve table used by the runtime.

Run from the repository root::

    python tools/build_sodium_relative_risks.py
"""

from __future__ import annotations

import json
from pathlib import Path
import urllib.parse
import urllib.request

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "src" / "mealhealth" / "data" / "sodium_relative_risks.csv"
BOP_API_BASE = "https://vizhub.healthdata.org/burden-of-proof/api/v1"
BOP_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0"
)

CURVES = {
    # curve_cause: (path, rei_id, cause_id, unit, expected stars)
    "CHD": ("sbp", 107, 493, "mmHg", 5),
    "Stroke": ("sbp", 107, 494, "mmHg", 5),
    "CKD": ("sbp", 107, 589, "mmHg", 3),
    "StomachCancer": ("sodium", 124, 414, "g/day", 3),
}


def _get(endpoint: str, **params: int) -> object:
    query = urllib.parse.urlencode(params)
    url = f"{BOP_API_BASE}/{endpoint}?{query}"
    request = urllib.request.Request(  # noqa: S310 - pinned HTTPS host
        url,
        headers={
            "User-Agent": BOP_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://vizhub.healthdata.org/burden-of-proof/",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        return json.load(response)


def build_relative_risks() -> pd.DataFrame:
    """Fetch and validate the selected all-age mean BoP curves."""

    rows: list[dict[str, object]] = []
    for curve_cause, (path, rei_id, cause_id, unit, stars) in CURVES.items():
        metadata = _get("risk_cause_metadata", risk=rei_id, cause=cause_id)
        if metadata.get("risk_unit") != unit:
            raise ValueError(
                f"{curve_cause}: expected unit {unit!r}, got "
                f"{metadata.get('risk_unit')!r}"
            )
        if metadata.get("star_rating") != stars:
            raise ValueError(
                f"{curve_cause}: expected {stars} stars, got "
                f"{metadata.get('star_rating')!r}"
            )
        curve = _get("output_data", risk=rei_id, cause=cause_id)
        exposure = [float(point["risk"]) for point in curve]
        if (
            len(exposure) < 2
            or exposure != sorted(exposure)
            or len(set(exposure)) != len(exposure)
        ):
            raise ValueError(f"{curve_cause}: invalid exposure grid")
        for point in curve:
            low = float(point["linear_cause_lower"])
            mean = float(point["linear_cause"])
            high = float(point["linear_cause_upper"])
            if not 0 < low <= mean <= high:
                raise ValueError(f"{curve_cause}: invalid RR uncertainty ordering")
            rows.append(
                {
                    "path": path,
                    "curve_cause": curve_cause,
                    "exposure": float(point["risk"]),
                    "rr_mean": mean,
                    "rr_low": low,
                    "rr_high": high,
                    "risk_lower": float(metadata["risk_lower"]),
                    "risk_upper": float(metadata["risk_upper"]),
                    "star_rating": int(metadata["star_rating"]),
                    "rei_id": rei_id,
                    "cause_id": cause_id,
                }
            )
        print(f"BoP {path} -> {curve_cause}: {len(curve)} points")
    return pd.DataFrame(rows).sort_values(["path", "curve_cause", "exposure"])


def main() -> None:
    result = build_relative_risks()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(result)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
