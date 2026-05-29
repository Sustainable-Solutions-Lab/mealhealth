# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the caloric-substitution diet construction."""

import pytest

from mealhealth.foodgroups import RISK_FACTORS
from mealhealth.model import CountryBurden, build_substituted_diet


@pytest.fixture
def usa():
    return CountryBurden("USA")


def test_substitution_factor(usa):
    # f = (C_base - C_meal) / C_base
    diet = build_substituted_diet(usa, {"vegetables": 100}, 500.0, RISK_FACTORS)
    expected_f = (usa.baseline_kcal - 500.0) / usa.baseline_kcal
    assert diet.f == pytest.approx(expected_f)
    # exposure = f*baseline + meal
    assert diet.exposure["vegetables"] == pytest.approx(
        expected_f * usa.baseline["vegetables"] + 100.0
    )
    # untouched group is just scaled baseline
    assert diet.exposure["fruits"] == pytest.approx(expected_f * usa.baseline["fruits"])


def test_zero_meal_recovers_baseline(usa):
    diet = build_substituted_diet(usa, {}, 0.0, RISK_FACTORS)
    assert diet.f == pytest.approx(1.0)
    for r in RISK_FACTORS:
        assert diet.exposure[r] == pytest.approx(usa.baseline.get(r, 0.0))


def test_meal_exceeds_baseline_clamps_and_warns(usa):
    big = usa.baseline_kcal + 1000.0
    diet = build_substituted_diet(usa, {"red_meat": 200}, big, RISK_FACTORS)
    assert diet.f == 0.0
    assert any("entire day" in w for w in diet.warnings)
    # diet is meal-only
    assert diet.exposure["red_meat"] == pytest.approx(200.0)
    assert diet.exposure["fruits"] == pytest.approx(0.0)


def test_negative_kcal_rejected(usa):
    with pytest.raises(ValueError):
        build_substituted_diet(usa, {}, -1.0, RISK_FACTORS)
