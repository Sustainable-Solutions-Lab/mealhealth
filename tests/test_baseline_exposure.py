# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the canonical direct-exposure baseline."""

from mealhealth import data


def test_direct_baseline_has_complete_factor_and_proxy_coverage():
    exposure = data.baseline_exposure()
    countries = set(data.available_countries())
    assert len(exposure) == 175 * 8
    assert set(exposure["country"]) == countries
    assert set(exposure["risk_factor"]) == {
        "fruits",
        "vegetables",
        "whole_grains",
        "legumes",
        "nuts_seeds",
        "red_meat",
        "processed_meat",
        "omega3",
    }
    proxies = exposure[exposure["source_country"] != exposure["country"]]
    assert set(
        proxies[["country", "source_country"]].itertuples(index=False, name=None)
    ) == {("GUF", "FRA")}


def test_calorie_baseline_has_provenance_and_country_coverage():
    calories = data.baseline_calories()
    assert len(calories) == 175
    assert set(calories["country"]) == set(data.available_countries())
    assert set(calories["source_year"]) == {2020}
    assert calories.loc[calories["country"] == "AFG", "source_country"].item() == "IRN"
