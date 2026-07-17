# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Integration tests and US sanity checks for the public assessment API."""

import math

import pytest

import mealhealth as mh
from mealhealth import data
from mealhealth.model import (
    ADULT_AGES,
    CountryBurden,
    RelativeRiskCurves,
    _population_log_rr,
)

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
    assert r.delta_yll_local_total == pytest.approx(0.0, abs=1e-9)
    assert r.delta_yll_standard_total == pytest.approx(0.0, abs=1e-9)
    for c in r.causes.values():
        assert c.paf_local == pytest.approx(0.0, abs=1e-12)
        assert c.delta_yll_standard == pytest.approx(0.0, abs=1e-9)


def test_omitted_omega3_preserves_existing_assessment():
    kwargs = {"meal": {"vegetables": 100}, "meal_kcal": 300, "country": "USA"}
    omitted = mh.assess_meal(**kwargs)
    explicit_none = mh.assess_meal(**kwargs, seafood_omega3_mg=None)
    assert "omega3" not in omitted.exposure
    assert "omega3" not in omitted.risk_attribution_local
    assert "omega3" not in omitted.risk_attribution_standard
    assert explicit_none.delta_yll_local_total == pytest.approx(
        omitted.delta_yll_local_total
    )
    assert explicit_none.delta_yll_standard_total == pytest.approx(
        omitted.delta_yll_standard_total
    )


# --------------------------------------------------------------------------
# US sanity: sign and direction
# --------------------------------------------------------------------------


def test_healthy_meal_gains_years_usa():
    r = mh.assess_meal(
        {"vegetables": 250, "whole_grains": 100, "legumes": 80, "fruits": 150},
        meal_kcal=500,
        country="USA",
    )
    assert r.delta_yll_local_total > 0  # protective groups -> years gained
    assert r.delta_yll_standard_total > r.delta_yll_local_total
    for c in ["CHD", "Stroke", "T2DM"]:
        assert r.causes[c].paf_local >= -1e-9


def test_unhealthy_meal_loses_years_usa():
    r = mh.assess_meal(
        {"red_meat": 150, "processed_meat": 60}, meal_kcal=650, country="USA"
    )
    assert r.delta_yll_local_total < 0  # lots of meat -> years lost
    assert r.causes["CRC"].paf_local < 0


def test_individual_meat_meal_loses_years_usa():
    r = mh.assess_meal(
        {"red_meat": 150, "processed_meat": 60},
        meal_kcal=650,
        country="USA",
        mode="age",
        age=45,
    )
    assert r.delta_yll_local_total < 0
    # marginal per-meal attribution is tiny and same sign
    pm = mh.per_meal_marginal(r)
    assert pm < 0
    assert abs(pm) < abs(r.delta_yll_local_total)


def test_population_vs_individual_scale():
    """Population mode is an annual population total; individual is per-person
    lifetime. They are different quantities but should share sign for the same
    meal."""
    meal = {"red_meat": 120, "processed_meat": 40}
    rp = mh.assess_meal(meal, 600, "USA", mode="population")
    ri = mh.assess_meal(meal, 600, "USA", mode="age", age=50)
    assert (rp.delta_yll_local_total < 0) == (ri.delta_yll_local_total < 0)
    # population-annual total (whole country) is far larger in magnitude
    assert abs(rp.delta_yll_local_total) > abs(ri.delta_yll_local_total)


def test_seafood_omega3_improves_chd():
    omitted = mh.assess_meal({}, 500, "USA")
    supplied = mh.assess_meal({}, 500, "USA", seafood_omega3_mg=500)
    assert supplied.causes["CHD"].paf_local > omitted.causes["CHD"].paf_local
    assert supplied.causes["CHD"].paf_standard > omitted.causes["CHD"].paf_standard
    assert supplied.risk_attribution_local["omega3"] > 0
    assert supplied.risk_attribution_standard["omega3"] > 0
    expected = supplied.f * supplied.baseline_exposure["omega3"] + 0.500
    assert supplied.exposure["omega3"] == pytest.approx(expected)


def test_explicit_zero_omega3_is_not_omission():
    omitted = mh.assess_meal({}, 500, "USA")
    zero = mh.assess_meal({}, 500, "USA", seafood_omega3_mg=0.0)
    assert "omega3" in zero.exposure
    assert zero.causes["CHD"].paf_local < omitted.causes["CHD"].paf_local
    assert zero.causes["CHD"].paf_standard < omitted.causes["CHD"].paf_standard
    assert zero.risk_attribution_local["omega3"] < 0
    assert zero.risk_attribution_standard["omega3"] < 0


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf"), -float("inf")])
def test_invalid_omega3_amount_rejected(value):
    with pytest.raises(ValueError, match="seafood_omega3_mg"):
        mh.assess_meal({}, 500, "USA", seafood_omega3_mg=value)


@pytest.mark.parametrize("mode,age", [("population", None), ("age", 60)])
def test_omega3_paf_matches_curve_knot_handcalc(mode, age):
    burden = CountryBurden("USA")
    curves = RelativeRiskCurves()
    baseline = burden.baseline["omega3"]
    target = 0.565
    omega3_mg = (target - baseline) * 1000.0
    result = mh.assess_meal(
        {}, 0.0, "USA", mode=mode, age=age, seafood_omega3_mg=omega3_mg
    )
    if mode == "population":
        delta = {"local": 0.0, "standard": 0.0}
        for age_band in ADULT_AGES:
            log_base = curves.log_rr("omega3", "CHD", age_band, baseline)
            log_target = curves.log_rr("omega3", "CHD", age_band, target)
            paf = 1.0 - math.exp(log_target - log_base)
            for sex in ("male", "female"):
                for life_table in ("local", "standard"):
                    delta[life_table] += (
                        burden.yll_by_stratum(
                            "CHD", age_band, sex, life_table=life_table
                        )
                        * paf
                    )
        expected_local = delta["local"] / burden.total_yll("CHD", life_table="local")
        expected_standard = delta["standard"] / burden.total_yll(
            "CHD", life_table="standard"
        )
    else:
        log_base = curves.log_rr("omega3", "CHD", "60-64", baseline)
        log_target = curves.log_rr("omega3", "CHD", "60-64", target)
        expected_local = 1.0 - math.exp(log_target - log_base)
        expected_standard = expected_local
    assert result.causes["CHD"].paf_local == pytest.approx(expected_local)
    assert result.causes["CHD"].paf_standard == pytest.approx(expected_standard)


# --------------------------------------------------------------------------
# Attribution and relative-only
# --------------------------------------------------------------------------


def test_attribution_sums_to_total():
    r = mh.assess_meal(
        {"vegetables": 200, "red_meat": 100, "processed_meat": 30},
        meal_kcal=600,
        country="USA",
    )
    assert sum(r.risk_attribution_local.values()) == pytest.approx(
        r.delta_yll_local_total, rel=1e-6
    )
    assert sum(r.risk_attribution_standard.values()) == pytest.approx(
        r.delta_yll_standard_total, rel=1e-6
    )


def test_explicit_local_names_alias_backward_compatible_names():
    result = mh.assess_meal({"vegetables": 200}, 300, "USA")
    assert result.delta_yll_local_total == result.delta_yll_total
    assert result.risk_attribution_local is result.risk_attribution
    for cause in result.causes.values():
        assert cause.paf_local == cause.paf
        assert cause.delta_yll_local == cause.delta_yll
        assert cause.rr_baseline_local == cause.rr_baseline
        assert cause.rr_meal_local == cause.rr_meal


def test_relative_only_matches_full_paf():
    meal = {"red_meat": 120, "vegetables": 150}
    full = mh.assess_meal(meal, 500, "USA")
    rel = mh.assess_meal(meal, 500, "USA", relative_only=True)
    assert rel.delta_yll_local_total == pytest.approx(0.0)
    assert rel.delta_yll_standard_total == pytest.approx(0.0)
    for c in full.causes:
        assert rel.causes[c].paf_local == pytest.approx(full.causes[c].paf_local)
        assert rel.causes[c].delta_yll_standard == pytest.approx(0.0)


def test_processed_meat_toggle():
    meal = {"processed_meat": 80}
    with_pm = mh.assess_meal(meal, 400, "USA")
    without_pm = mh.assess_meal(meal, 400, "USA", include_processed_meat=False)
    # excluding processed meat removes its (harmful) contribution
    assert with_pm.delta_yll_local_total < without_pm.delta_yll_local_total
    assert "processed_meat" not in without_pm.exposure


def test_unknown_food_group_raises():
    with pytest.raises(ValueError):
        mh.assess_meal({"chocolate": 50}, 200, "USA")


def test_age_mode_requires_age():
    with pytest.raises(ValueError):
        mh.assess_meal({"vegetables": 100}, 200, "USA", mode="age")


@pytest.mark.parametrize("age", [24.9, -1, float("nan"), float("inf"), "unknown"])
def test_age_mode_rejects_values_outside_adult_risk_curves(age):
    with pytest.raises(ValueError, match="at least 25"):
        mh.assess_meal({"vegetables": 100}, 200, "USA", mode="age", age=age)


# --------------------------------------------------------------------------
# Plumbing: age-weighting
# --------------------------------------------------------------------------


def test_population_log_rr_reduces_to_single_age():
    burden = CountryBurden("USA")
    curves = RelativeRiskCurves()
    # force all YLL weight onto one age band
    for key in burden._age_weights_local:
        burden._age_weights_local[key] = 0.0
    burden._age_weights_local[("CHD", "60-64")] = 1.0
    direct = curves.log_rr("red_meat", "CHD", "60-64", 100.0)
    weighted = _population_log_rr(
        curves, burden, "red_meat", "CHD", 100.0, life_table="local"
    )
    assert weighted == pytest.approx(direct)


# --------------------------------------------------------------------------
# US baseline burden sanity (order of magnitude)
# --------------------------------------------------------------------------


def test_usa_baseline_burden_reasonable():
    b = CountryBurden("USA")
    # US total YLL for CHD should be in the millions of years (deaths ~ 4/1000
    # at older ages x large older population x ~15-20 yr life exp).
    assert 1e6 < b.total_yll("CHD", life_table="local") < 5e7
    assert b.total_yll("CHD", life_table="standard") > b.total_yll(
        "CHD", life_table="local"
    )
    # baseline calories ~2400 kcal
    assert 1800 < b.baseline_kcal < 3200
    # GBD 2023 direct baselines are on the model basis; the USA split is about
    # 111 g/day in this release.
    assert b.baseline["red_meat"] + b.baseline["processed_meat"] == pytest.approx(
        111.3, abs=1.0
    )
    assert b.baseline["omega3"] == pytest.approx(0.3110668163)


def test_missing_country_nutrient_baseline_raises(monkeypatch):
    from mealhealth import data

    incomplete = data.baseline_exposure().query("country != 'USA'")
    monkeypatch.setattr(data, "baseline_exposure", lambda: incomplete)
    with pytest.raises(ValueError, match="missing USA"):
        CountryBurden("USA")


def test_standard_life_table_values():
    lt = data.standard_life_table()
    assert len(lt) == 21
    ex = dict(lt[["age", "ex"]].itertuples(index=False, name=None))
    assert ex["<1"] == pytest.approx(89.95803974533831)
    assert ex["70-74"] == pytest.approx(22.160212679066483)
    assert ex["95+"] == pytest.approx(8.494693425849968)
