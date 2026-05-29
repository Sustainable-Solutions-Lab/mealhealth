# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the relative-risk curve interpolation and bundled data shape."""

import math

import pandas as pd
import pytest

from mealhealth import data
from mealhealth.foodgroups import ADULT_AGES, CAUSES, RISK_FACTORS
from mealhealth.model import RelativeRiskCurves


def test_bundled_data_present():
    rr = data.relative_risks()
    assert set(rr["risk_factor"]) == set(RISK_FACTORS)
    assert set(rr["cause"]) <= set(CAUSES)
    # every (risk, cause, age) has all 15 adult ages
    counts = rr.groupby(["risk_factor", "cause"])["age"].nunique()
    assert (counts == len(ADULT_AGES)).all()


def test_cause_maps_match_gbd():
    curves = RelativeRiskCurves()
    assert set(curves.causes_for("legumes")) == {"CHD"}
    assert set(curves.causes_for("vegetables")) == {"CHD", "Stroke"}
    assert set(curves.causes_for("nuts_seeds")) == {"CHD", "T2DM"}
    assert set(curves.causes_for("fruits")) == {"CHD", "Stroke", "T2DM"}
    assert set(curves.causes_for("red_meat")) == {"CHD", "Stroke", "T2DM", "CRC"}
    # GBD processed meat: no stroke
    assert set(curves.causes_for("processed_meat")) == {"CHD", "T2DM", "CRC"}


def test_log_linear_interpolation_midpoint():
    """Interpolation is linear in log-space between knots."""
    df = pd.DataFrame(
        {
            "risk_factor": "x",
            "cause": "CHD",
            "age": "25-29",
            "exposure_g_per_day": [0.0, 100.0, 200.0],
            "rr_mean": [1.5, 1.0, 0.8],
        }
    )
    curves = RelativeRiskCurves(df)
    # halfway (50) between RR 1.5 and 1.0 in log space -> sqrt(1.5*1.0)
    rr_50 = math.exp(curves.log_rr("x", "CHD", "25-29", 50.0))
    assert rr_50 == pytest.approx(math.sqrt(1.5 * 1.0))


def test_clamps_outside_data_range():
    df = pd.DataFrame(
        {
            "risk_factor": "x",
            "cause": "CHD",
            "age": "25-29",
            "exposure_g_per_day": [0.0, 100.0],
            "rr_mean": [1.0, 0.9],
        }
    )
    curves = RelativeRiskCurves(df)
    assert curves.log_rr("x", "CHD", "25-29", -10) == pytest.approx(math.log(1.0))
    assert curves.log_rr("x", "CHD", "25-29", 500) == pytest.approx(math.log(0.9))


def test_protective_groups_have_decreasing_rr():
    rr = data.relative_risks()
    for risk in ["fruits", "vegetables", "whole_grains", "legumes", "nuts_seeds"]:
        sub = rr[(rr["risk_factor"] == risk) & (rr["age"] == "25-29")]
        for _, g in sub.groupby("cause"):
            g = g.sort_values("exposure_g_per_day")
            assert g["rr_mean"].iloc[-1] <= g["rr_mean"].iloc[0] + 1e-9


def test_harmful_groups_have_increasing_rr():
    rr = data.relative_risks()
    for risk in ["red_meat", "processed_meat"]:
        sub = rr[(rr["risk_factor"] == risk) & (rr["age"] == "25-29")]
        for _, g in sub.groupby("cause"):
            g = g.sort_values("exposure_g_per_day")
            assert g["rr_mean"].iloc[-1] >= g["rr_mean"].iloc[0] - 1e-9
