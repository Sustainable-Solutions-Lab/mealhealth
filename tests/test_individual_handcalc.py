# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Hand-calculation validation of the individual lifetime YLL anchor.

The spec flags the individual formulation as "the key thing to validate against
hand-calculations before building out":

    dYLL_d = sum_{a>=a0} S(a|a0) . (m_{d,a} . span_a) . e_a . PAF_{d,a}

This test drives ``_assess_individual`` with fully controlled stubs (a 2-band
life table, a flat 2-point RR curve) so the expected result can be computed by
hand, then checks the engine reproduces it.
"""

import math

import pytest

from mealhealth.foodgroups import age_to_bucket
from mealhealth.model import SubstitutedDiet, _assess_individual


class FakeCurves:
    """A single red_meat->CHD curve, age-independent and known."""

    pairs = {("red_meat", "CHD")}

    def log_rr(self, risk, cause, age, intake):
        # baseline intake 10 -> RR 1.1; meal intake 60 -> RR 1.3; flat by age
        return math.log(1.1) if intake <= 10.0 else math.log(1.3)


class FakeBurden:
    """2-band life table; mortality only in the first two adult bands >= a0."""

    def __init__(self):
        self.death_rate = {("CHD", "40-44"): 0.002, ("CHD", "45-49"): 0.004}
        self.local_ex = {"40-44": 40.0, "45-49": 35.0}
        self.standard_ex = {"40-44": 50.0, "45-49": 45.0}
        self._surv = {"40-44": 1.0, "45-49": 0.9}

    def conditional_survival(self, age, a0_bucket):
        return self._surv.get(age, 0.0)

    def age_span_years(self, age):
        return 5.0

    def death_rate_get(self, key, default):  # not used; dict.get is called
        return self.death_rate.get(key, default)


def test_individual_yll_matches_hand_calc():
    a0 = 40.0
    diet = SubstitutedDiet(
        f=0.0,
        exposure={"red_meat": 60.0},
        baseline_exposure={"red_meat": 10.0},
    )
    causes = _assess_individual(
        FakeCurves(), FakeBurden(), diet, ("red_meat",), a0, relative_only=False
    )

    # PAF = 1 - RR_meal/RR_base = 1 - 1.3/1.1 (a harm: negative)
    paf = 1.0 - 1.3 / 1.1
    expected = paf * (
        1.0 * (0.002 * 5.0) * 40.0  # 40-44 band
        + 0.9 * (0.004 * 5.0) * 35.0  # 45-49 band
    )
    assert causes["CHD"].paf_local == pytest.approx(paf)
    assert causes["CHD"].delta_yll_local == pytest.approx(expected)
    expected_standard = paf * (1.0 * (0.002 * 5.0) * 50.0 + 0.9 * (0.004 * 5.0) * 45.0)
    assert causes["CHD"].delta_yll_standard == pytest.approx(expected_standard)
    assert expected < 0  # eating more red meat loses years


def test_a0_bucketing():
    assert age_to_bucket(40) == "40-44"
    assert age_to_bucket(44.9) == "40-44"
    assert age_to_bucket(45) == "45-49"
    assert age_to_bucket(0.5) == "<1"
    assert age_to_bucket(97) == "95+"


def test_relative_only_individual_zeroes_yll_keeps_paf():
    diet = SubstitutedDiet(
        f=0.0, exposure={"red_meat": 60.0}, baseline_exposure={"red_meat": 10.0}
    )
    causes = _assess_individual(
        FakeCurves(), FakeBurden(), diet, ("red_meat",), 40.0, relative_only=True
    )
    assert causes["CHD"].delta_yll_local == 0.0
    assert causes["CHD"].delta_yll_standard == 0.0
    assert causes["CHD"].paf_local == pytest.approx(1.0 - 1.3 / 1.1)
