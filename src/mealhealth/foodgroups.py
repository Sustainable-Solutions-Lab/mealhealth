# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Definitions of the dietary risk-factor food groups and disease causes.

A *risk factor* here is a GBD dietary exposure group whose intake changes the
relative risk of one or more diseases. A meal is described to the tool in terms
of grams of each of these groups (plus a total calorie figure). Foods that fall
outside every risk group (poultry, eggs, oils, refined grains, etc.) do not
enter the food-group calculation directly; they affect the result only through
caloric displacement of the baseline diet. Seafood EPA+DHA and elemental
sodium can additionally be supplied as optional nutrient factors.

Mass basis
----------
Each group has a *required input basis* — the physical state in which its mass
should be supplied. These match the basis in which the bundled relative-risk
curves and baseline diet are expressed, so they must be respected for the
numbers to be meaningful. Most groups are fresh / as-eaten weight; cereals,
legumes and nuts are dry (uncooked) weight, which is how GBD defines their
exposure. See :data:`FOOD_GROUPS` and ``docs/food_groups.md``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FoodGroup:
    """A GBD dietary risk-factor group."""

    name: str
    label: str
    input_basis: str
    description: str
    # True for groups that are harmful with increasing intake (RR rises),
    # False for protective groups (RR falls with intake).
    harmful: bool


@dataclass(frozen=True)
class NutrientFactor:
    """An optional nutrient exposure supplied separately from food-group mass."""

    name: str
    label: str
    api_unit: str
    api_to_internal: float
    description: str
    harmful: bool


FOOD_GROUPS: dict[str, FoodGroup] = {
    "fruits": FoodGroup(
        "fruits",
        "Fruits",
        "fresh weight (as eaten)",
        "Fresh, frozen, cooked, canned or dried fruit, excluding fruit juices "
        "and salted/pickled fruits.",
        harmful=False,
    ),
    "vegetables": FoodGroup(
        "vegetables",
        "Vegetables",
        "fresh weight (as eaten)",
        "Fresh, frozen, cooked, canned or dried vegetables, excluding legumes, "
        "salted/pickled vegetables, juices, nuts/seeds and starchy vegetables.",
        harmful=False,
    ),
    "whole_grains": FoodGroup(
        "whole_grains",
        "Whole grains",
        "dry weight (uncooked)",
        "Whole grains (bran, germ and endosperm in natural proportion) from "
        "cereals, bread, rice, pasta, etc. Supplied as dry/uncooked weight.",
        harmful=False,
    ),
    "legumes": FoodGroup(
        "legumes",
        "Legumes",
        "dry weight (uncooked)",
        "Legumes and pulses (beans, lentils, peas), fresh, frozen, cooked, "
        "canned or dried. Supplied as dry/uncooked weight.",
        harmful=False,
    ),
    "nuts_seeds": FoodGroup(
        "nuts_seeds",
        "Nuts and seeds",
        "dry weight (as eaten)",
        "Tree nuts, seeds and peanuts.",
        harmful=False,
    ),
    "red_meat": FoodGroup(
        "red_meat",
        "Unprocessed red meat",
        "fresh raw weight (retail)",
        "Unprocessed red meat (beef, pork, lamb, goat), excluding processed "
        "meats, poultry, fish and eggs.",
        harmful=True,
    ),
    "processed_meat": FoodGroup(
        "processed_meat",
        "Processed meat",
        "fresh raw weight (retail)",
        "Meat preserved by smoking, curing, salting or chemical preservatives "
        "(bacon, ham, sausages, deli meats).",
        harmful=True,
    ),
}

#: Risk factors modelled by default. ``processed_meat`` is optional and can be
#: disabled by the caller.
RISK_FACTORS: tuple[str, ...] = (
    "fruits",
    "vegetables",
    "whole_grains",
    "legumes",
    "nuts_seeds",
    "red_meat",
    "processed_meat",
)

#: Optional nutrient risk factors. Values enter the public API in ``api_unit``
#: per daily meal and are converted to the model's g/day exposure axis.
DIRECT_NUTRIENT_FACTORS: dict[str, NutrientFactor] = {
    "omega3": NutrientFactor(
        "omega3",
        "Seafood omega-3 (EPA + DHA)",
        "mg",
        0.001,
        "Long-chain seafood omega-3 fatty acids EPA and DHA; excludes plant ALA.",
        harmful=False,
    )
}

#: Optional nutrient factors whose health effects are evaluated through a
#: stratum-resolved mediator rather than a direct country-level baseline.
MEDIATOR_FACTORS: dict[str, NutrientFactor] = {
    "sodium": NutrientFactor(
        "sodium",
        "Sodium",
        "mg",
        0.001,
        "Elemental dietary sodium from ingredients, cooking salt, sauces, and "
        "table salt. The model converts it to 24-hour urinary sodium and "
        "models a mean systolic-blood-pressure shift.",
        harmful=True,
    )
}

#: Every optional nutrient exposed by the public API.
NUTRIENT_FACTORS: dict[str, NutrientFactor] = {
    **DIRECT_NUTRIENT_FACTORS,
    **MEDIATOR_FACTORS,
}

#: Every factor for which bundled baseline and relative-risk data exist. An
#: assessment uses all selected food groups plus only nutrients explicitly
#: supplied by the caller.
MODEL_RISK_FACTORS: tuple[str, ...] = RISK_FACTORS + tuple(NUTRIENT_FACTORS)

#: Disease causes modelled.
CAUSES: tuple[str, ...] = (
    "CHD",
    "Stroke",
    "T2DM",
    "CRC",
    "StomachCancer",
    "HaemorrhagicStroke",
    "CKD",
)

CAUSE_LABELS: dict[str, str] = {
    "CHD": "Coronary (ischemic) heart disease",
    "Stroke": "Ischemic stroke",
    "T2DM": "Type 2 diabetes mellitus",
    "CRC": "Colorectal cancer",
    "StomachCancer": "Stomach cancer",
    "HaemorrhagicStroke": "Haemorrhagic stroke",
    "CKD": "Chronic kidney disease",
}

#: Ordered age buckets shared by all per-age data (population, mortality,
#: life table, age-specific relative risks for adults are the 25+ subset).
AGE_BUCKETS: tuple[str, ...] = (
    "<1",
    "1-4",
    "5-9",
    "10-14",
    "15-19",
    "20-24",
    "25-29",
    "30-34",
    "35-39",
    "40-44",
    "45-49",
    "50-54",
    "55-59",
    "60-64",
    "65-69",
    "70-74",
    "75-79",
    "80-84",
    "85-89",
    "90-94",
    "95+",
)

#: Adult age buckets for which GBD provides dietary relative risks (>= 25 y).
ADULT_AGES: tuple[str, ...] = AGE_BUCKETS[6:]

#: Width in years of each age bucket. The open-ended 95+ interval is handled
#: separately (its effective width is the remaining life expectancy at 95+).
AGE_SPAN: dict[str, float] = {
    "<1": 1.0,
    "1-4": 4.0,
    **{a: 5.0 for a in AGE_BUCKETS[2:]},
}

#: Lower bound (exact age) of each bucket.
AGE_START: dict[str, int] = {
    "<1": 0,
    "1-4": 1,
    **{a: int(a.split("-")[0]) for a in AGE_BUCKETS[2:-1]},
    "95+": 95,
}


def age_to_bucket(age: float) -> str:
    """Return the age bucket label containing ``age`` (years)."""
    if age < 1:
        return "<1"
    if age < 5:
        return "1-4"
    if age >= 95:
        return "95+"
    lo = int(age // 5) * 5
    return f"{lo}-{lo + 4}"
