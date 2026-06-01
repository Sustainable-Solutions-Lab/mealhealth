# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Integration tests and US sanity checks for the public assessment API."""

import pytest

import mealhealth as mh
from mealhealth.model import CountryBurden, RelativeRiskCurves, _population_log_rr

# --------------------------------------------------------------------------
# Country coverage
# --------------------------------------------------------------------------


def test_country_coverage():
    countries = mh.list_countries()
    assert "USA" in countries
    assert len(countries) > 150
    assert all(len(c) == 3 for c in countries)


def test_unknown_country_raises():
    with pytest.raises(KeyError):
        mh.assess_meal({"vegetables": 100}, 200, "ZZZ")


# --------------------------------------------------------------------------
# Zero / identity behaviour
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,age", [("population", None), ("median", None), ("age", 50)]
)
def test_empty_meal_zero_effect(mode, age):
    r = mh.assess_meal({}, 0.0, "USA", mode=mode, age=age)
    assert r.f == pytest.approx(1.0)
    assert r.delta_yll_total == pytest.approx(0.0, abs=1e-9)
    for c in r.causes.values():
        assert c.paf == pytest.approx(0.0, abs=1e-12)


# --------------------------------------------------------------------------
# US sanity: sign and direction
# --------------------------------------------------------------------------


def test_healthy_meal_gains_years_usa():
    r = mh.assess_meal(
        {"vegetables": 250, "whole_grains": 100, "legumes": 80, "fruits": 150},
        meal_kcal=500,
        country="USA",
    )
    assert r.delta_yll_total > 0  # protective groups -> years gained
    for c in ["CHD", "Stroke", "T2DM"]:
        assert r.causes[c].paf >= -1e-9


def test_unhealthy_meal_loses_years_usa():
    r = mh.assess_meal(
        {"red_meat": 150, "processed_meat": 60}, meal_kcal=650, country="USA"
    )
    assert r.delta_yll_total < 0  # lots of meat -> years lost
    assert r.causes["CRC"].paf < 0


def test_individual_meat_meal_loses_years_usa():
    r = mh.assess_meal(
        {"red_meat": 150, "processed_meat": 60},
        meal_kcal=650,
        country="USA",
        mode="age",
        age=45,
    )
    assert r.delta_yll_total < 0
    # marginal per-meal attribution is tiny and same sign
    pm = mh.per_meal_marginal(r)
    assert pm < 0
    assert abs(pm) < abs(r.delta_yll_total)


def test_population_vs_individual_scale():
    """Population mode is an annual population total; individual is per-person
    lifetime. They are different quantities but should share sign for the same
    meal."""
    meal = {"red_meat": 120, "processed_meat": 40}
    rp = mh.assess_meal(meal, 600, "USA", mode="population")
    ri = mh.assess_meal(meal, 600, "USA", mode="age", age=50)
    assert (rp.delta_yll_total < 0) == (ri.delta_yll_total < 0)
    # population-annual total (whole country) is far larger in magnitude
    assert abs(rp.delta_yll_total) > abs(ri.delta_yll_total)


# --------------------------------------------------------------------------
# Attribution and relative-only
# --------------------------------------------------------------------------


def test_attribution_sums_to_total():
    r = mh.assess_meal(
        {"vegetables": 200, "red_meat": 100, "processed_meat": 30},
        meal_kcal=600,
        country="USA",
    )
    assert sum(r.risk_attribution.values()) == pytest.approx(
        r.delta_yll_total, rel=1e-6
    )


def test_relative_only_matches_full_paf():
    meal = {"red_meat": 120, "vegetables": 150}
    full = mh.assess_meal(meal, 500, "USA")
    rel = mh.assess_meal(meal, 500, "USA", relative_only=True)
    assert rel.delta_yll_total == pytest.approx(0.0)
    for c in full.causes:
        assert rel.causes[c].paf == pytest.approx(full.causes[c].paf)


def test_processed_meat_toggle():
    meal = {"processed_meat": 80}
    with_pm = mh.assess_meal(meal, 400, "USA")
    without_pm = mh.assess_meal(meal, 400, "USA", include_processed_meat=False)
    # excluding processed meat removes its (harmful) contribution
    assert with_pm.delta_yll_total < without_pm.delta_yll_total
    assert "processed_meat" not in without_pm.exposure


def test_unknown_food_group_raises():
    with pytest.raises(ValueError):
        mh.assess_meal({"chocolate": 50}, 200, "USA")


def test_age_mode_requires_age():
    with pytest.raises(ValueError):
        mh.assess_meal({"vegetables": 100}, 200, "USA", mode="age")


# --------------------------------------------------------------------------
# Plumbing: age-weighting
# --------------------------------------------------------------------------


def test_population_log_rr_reduces_to_single_age():
    burden = CountryBurden("USA")
    curves = RelativeRiskCurves()
    # force all YLL weight onto one age band
    for key in burden._age_weights:
        burden._age_weights[key] = 0.0
    burden._age_weights[("CHD", "60-64")] = 1.0
    direct = curves.log_rr("red_meat", "CHD", "60-64", 100.0)
    weighted = _population_log_rr(curves, burden, "red_meat", "CHD", 100.0)
    assert weighted == pytest.approx(direct)


# --------------------------------------------------------------------------
# US baseline burden sanity (order of magnitude)
# --------------------------------------------------------------------------


def test_usa_baseline_burden_reasonable():
    b = CountryBurden("USA")
    # US total YLL for CHD should be in the millions of years (deaths ~ 4/1000
    # at older ages x large older population x ~15-20 yr life exp).
    assert 1e6 < b.total_yll("CHD") < 5e7
    # baseline calories ~2400 kcal
    assert 1800 < b.baseline_kcal < 3200
    # red + processed meat split sums to the combined red-meat intake ~66.6 g/day
    assert b.baseline["red_meat"] + b.baseline["processed_meat"] == pytest.approx(
        66.6, abs=1.0
    )
