# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Regeneration checks for omega-3 relative-risk inputs."""

import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "tools" / "prepare_data.py"
SPEC = importlib.util.spec_from_file_location("prepare_data", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
prepare = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prepare
SPEC.loader.exec_module(prepare)


def test_omega3_bop_metadata_and_tmrel():
    assert prepare.GBD_REI_ID["omega3"] == 121
    assert prepare.GBD_CAUSE_ID["CHD"] == 493
    assert prepare.RISK_CAUSE_MAP["omega3"] == ["CHD"]
    assert "omega3" not in prepare.RR_BASIS_FACTOR

    tmrel = pd.read_csv(ROOT / "tools" / "reference" / "rr_tmrel.csv").set_index(
        "risk_factor"
    )
    row = tmrel.loc["omega3"]
    assert row["risk_type"] == "protective"
    assert 0.5 * (row["tmrel_low"] + row["tmrel_high"]) == pytest.approx(0.565)


def test_omega3_age_attenuation_has_all_adult_ages():
    attenuation = pd.read_csv(ROOT / "tools" / "reference" / "rr_age_attenuation.csv")
    omega3 = attenuation.query("risk_factor == 'omega3' and cause == 'CHD'")
    assert set(omega3["age"]) == set(prepare.ADULT_AGE_LABELS)
    assert len(omega3) == 15
    assert omega3.set_index("age").loc["60-64", "beta"] == pytest.approx(1.0)


def test_incomplete_bop_cache_is_refreshed(tmp_path, monkeypatch):
    cache = tmp_path / "bop.csv"
    pd.DataFrame(
        [
            {
                "risk_factor": "fruits",
                "cause": "CHD",
                "exposure_g_per_day": 0.0,
                "rr_mean": 1.0,
                "rr_low": 1.0,
                "rr_high": 1.0,
            }
        ]
    ).to_csv(cache, index=False)

    rows = []
    for risk, causes in prepare.RISK_CAUSE_MAP.items():
        for cause in causes:
            rows.append(
                {
                    "risk_factor": risk,
                    "cause": cause,
                    "exposure_g_per_day": 0.0,
                    "rr_mean": 1.0,
                    "rr_low": 1.0,
                    "rr_high": 1.0,
                }
            )
    refreshed = pd.DataFrame(rows)
    calls = []
    monkeypatch.setattr(prepare, "BOP_CURVES_CSV", cache)
    monkeypatch.setattr(
        prepare, "_fetch_bop_curves", lambda: calls.append(True) or refreshed
    )
    result = prepare._load_bop_curves()
    assert calls == [True]
    assert set(result["risk_factor"]) >= {"omega3"}
    assert set(pd.read_csv(cache)["risk_factor"]) >= {"omega3"}
