# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the real-data central sodium mean-shift implementation."""

import math

import numpy as np
import pandas as pd
import pytest

import mealhealth as mh
from mealhealth import data
from mealhealth.foodgroups import ADULT_AGES
from mealhealth.sodium import (
    MEDIATED_CURVE_BY_CAUSE,
    SODIUM_TO_SBP_MMHG_PER_G,
    SODIUM_URINARY_RECOVERY,
    SodiumMeanShiftModel,
)


def _synthetic_curves() -> pd.DataFrame:
    rows = []
    for path, cause, slope in (
        ("sbp", "CHD", 0.01),
        ("sbp", "Stroke", 0.01),
        ("sbp", "CKD", 0.01),
        ("sodium", "StomachCancer", 0.1),
    ):
        for exposure in (0.0, 300.0 if path == "sbp" else 10.0):
            rr = math.exp(slope * exposure)
            rows.append(
                {
                    "path": path,
                    "curve_cause": cause,
                    "exposure": exposure,
                    "rr_mean": rr,
                    "rr_low": rr,
                    "rr_high": rr,
                    "risk_lower": 0.0,
                    "risk_upper": 300.0 if path == "sbp" else 10.0,
                    "star_rating": 5,
                    "rei_id": 1,
                    "cause_id": 1,
                }
            )
    return pd.DataFrame(rows)


def _synthetic_mediators() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "country": "TST",
                "age": "60-64",
                "sex": sex,
                "sodium_urinary_g_per_day_mean": 4.0,
                "sbp_mmhg_mean": 130.0,
            }
            for sex in ("male", "female")
        ]
    )


def test_central_mean_shift_matches_closed_form(monkeypatch):
    monkeypatch.setattr(data, "baseline_mediators", _synthetic_mediators)
    monkeypatch.setattr(data, "sodium_relative_risks", _synthetic_curves)
    monkeypatch.setattr(
        data,
        "sbp_age_attenuation",
        lambda: pd.DataFrame(
            [
                {"curve_cause": cause, "age": "60-64", "beta": 2.0}
                for cause in {
                    "CHD",
                    "Stroke",
                    "CKD",
                }
            ]
        ),
    )
    model = SodiumMeanShiftModel("TST")
    effect = model.stratum_effect(
        "CHD", "60-64", "male", baseline_scale=0.5, meal_sodium_g=1.0
    )
    assert effect.meal_urinary_g == pytest.approx(2.0 + SODIUM_URINARY_RECOVERY)
    assert effect.meal_effective_g == pytest.approx(3.0)
    assert effect.delta_sbp_mmhg == pytest.approx(-SODIUM_TO_SBP_MMHG_PER_G)
    tmrel = np.linspace(1.0, 5.0, 100_001)
    baseline_effective = np.maximum(4.0, tmrel)
    meal_effective = np.maximum(2.0 + SODIUM_URINARY_RECOVERY, tmrel)
    sbp_ratio = np.exp(
        2.0 * 0.01 * SODIUM_TO_SBP_MMHG_PER_G * (meal_effective - baseline_effective)
    )
    assert effect.risk_ratio == pytest.approx(np.trapezoid(sbp_ratio, tmrel) / 4.0)

    stomach = model.stratum_effect(
        "StomachCancer",
        "60-64",
        "female",
        baseline_scale=0.5,
        meal_sodium_g=1.0,
    )
    stomach_ratio = np.exp(0.1 * (meal_effective - baseline_effective))
    assert stomach.risk_ratio == pytest.approx(np.trapezoid(stomach_ratio, tmrel) / 4.0)


def test_bundled_sodium_inputs_have_complete_supported_shape():
    curves = data.sodium_relative_risks()
    attenuation = data.sbp_age_attenuation()
    assert len(curves) == 400
    assert set(attenuation["age"]) == set(ADULT_AGES)
    assert set(MEDIATED_CURVE_BY_CAUSE) == {
        "CHD",
        "Stroke",
        "HaemorrhagicStroke",
        "CKD",
    }


def test_omitted_sodium_is_exactly_backward_compatible():
    kwargs = dict(meal={"vegetables": 100}, meal_kcal=300, country="USA")
    omitted = mh.assess_meal(**kwargs)
    explicit_none = mh.assess_meal(**kwargs, sodium_mg=None)
    assert omitted == explicit_none
    assert "sodium" not in omitted.exposure
    assert "sodium" not in omitted.risk_attribution_local


def test_explicit_zero_sodium_is_active_but_identity_without_displacement():
    result = mh.assess_meal({}, 0.0, "USA", sodium_mg=0.0)
    assert "sodium" in result.exposure
    assert result.exposure["sodium"] == pytest.approx(
        result.baseline_exposure["sodium"]
    )
    assert result.delta_yll_local_total == pytest.approx(0.0, abs=1e-9)
    assert result.delta_yll_standard_total == pytest.approx(0.0, abs=1e-9)


def test_more_sodium_worsens_all_supported_causes():
    low = mh.assess_meal({}, 500, "USA", sodium_mg=500)
    high = mh.assess_meal({}, 500, "USA", sodium_mg=2500)
    assert high.risk_attribution_local["sodium"] < low.risk_attribution_local["sodium"]
    sodium_causes = {"StomachCancer", *MEDIATED_CURVE_BY_CAUSE}
    for cause in sodium_causes:
        assert high.causes[cause].paf_local <= low.causes[cause].paf_local + 1e-12


def test_sodium_attribution_sums_with_other_risks():
    result = mh.assess_meal(
        {"vegetables": 180, "processed_meat": 30},
        550,
        "USA",
        seafood_omega3_mg=250,
        sodium_mg=1700,
    )
    assert sum(result.risk_attribution_local.values()) == pytest.approx(
        result.delta_yll_local_total, rel=1e-9
    )
    assert sum(result.risk_attribution_standard.values()) == pytest.approx(
        result.delta_yll_standard_total, rel=1e-9
    )


def test_individual_sodium_and_relative_only_use_same_current_age_paf():
    full = mh.assess_meal({}, 500, "USA", mode="age", age=50, sodium_mg=2500)
    relative = mh.assess_meal(
        {},
        500,
        "USA",
        mode="age",
        age=50,
        sodium_mg=2500,
        relative_only=True,
    )
    assert full.delta_yll_local_total < 0
    assert full.delta_yll_standard_total < 0
    assert relative.delta_yll_local_total == 0.0
    assert relative.delta_yll_standard_total == 0.0
    assert relative.delta_paf_local_total == pytest.approx(full.delta_paf_local_total)
    assert relative.delta_paf_standard_total == pytest.approx(
        full.delta_paf_standard_total
    )


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf"), -float("inf")])
def test_invalid_sodium_amount_rejected(value):
    with pytest.raises(ValueError, match="sodium_mg"):
        mh.assess_meal({}, 500, "USA", sodium_mg=value)


def test_public_nutrient_registry_includes_sodium():
    sodium = mh.nutrient_factors()["sodium"]
    assert sodium.api_unit == "mg"
    assert sodium.harmful
