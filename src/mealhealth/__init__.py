# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""mealhealth — a healthiness metric for a meal.

Given a meal in food-group terms, optional nutrient content, and calories,
estimate the change
in years of life lost (or gained) if an average person in a chosen country ate
this meal every day, relative to that country's baseline diet. Built on Global
Burden of Disease relative-risk dose-response curves.

Quick start
-----------
>>> import mealhealth as mh
>>> result = mh.assess_meal(
...     meal={"vegetables": 200, "whole_grains": 80, "legumes": 50},
...     meal_kcal=500,
...     country="USA",
... )
>>> print(result.summary())

NOTE ON LICENSING: the source code is GPL-3.0-or-later, but the bundled data is
derived from GBD, GDD-IA and WPP datasets; its non-commercial restriction comes
from IHME GBD, so the distributed package as a whole is for **non-commercial
use**. See ``docs/data_sources.md``.
"""

from .api import (
    CAUSE_LABELS,
    RISK_FACTORS,
    MealAssessment,
    assess_meal,
    food_groups,
    list_countries,
    nutrient_factors,
    per_meal_marginal,
)
from .foodgroups import (
    CAUSES,
    FOOD_GROUPS,
    MODEL_RISK_FACTORS,
    NUTRIENT_FACTORS,
    FoodGroup,
    NutrientFactor,
)

__version__ = "0.1.0"

__all__ = [
    "assess_meal",
    "per_meal_marginal",
    "list_countries",
    "food_groups",
    "nutrient_factors",
    "MealAssessment",
    "FoodGroup",
    "NutrientFactor",
    "FOOD_GROUPS",
    "RISK_FACTORS",
    "NUTRIENT_FACTORS",
    "MODEL_RISK_FACTORS",
    "CAUSES",
    "CAUSE_LABELS",
    "__version__",
]
