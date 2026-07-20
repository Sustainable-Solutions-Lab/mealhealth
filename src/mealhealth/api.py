# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Public API for the meal health indicator."""

from __future__ import annotations

from . import data
from .foodgroups import (
    CAUSE_LABELS,
    FOOD_GROUPS,
    NUTRIENT_FACTORS,
    RISK_FACTORS,
    FoodGroup,
    NutrientFactor,
)
from .model import MealAssessment, assess

# A nominal number of meals over an adult lifetime, used to express the
# lifetime effect as a per-meal marginal attribution. ~3 meals/day for
# ~60 adult years. This is a linear/marginal attribution, NOT a biological
# single-meal effect (see docs/methodology.md).
MEALS_PER_LIFETIME = 3 * 365 * 60


def assess_meal(
    meal: dict[str, float],
    meal_kcal: float,
    country: str,
    *,
    mode: str = "population",
    age: float | None = None,
    include_processed_meat: bool = True,
    relative_only: bool = False,
    seafood_omega3_mg: float | None = None,
    sodium_mg: float | None = None,
) -> MealAssessment:
    """Assess the health impact of eating ``meal`` every day in ``country``.

    Parameters
    ----------
    meal:
        Mapping of risk-factor food group -> grams in the meal, each in the
        group's required input basis (see :func:`food_groups`). Valid keys are
        the entries of :data:`mealhealth.RISK_FACTORS`. Foods outside these
        groups (poultry, fish, eggs, oils, refined grains, ...) are not listed
        here; their food mass enters only through ``meal_kcal``. Seafood EPA +
        DHA can be supplied separately with ``seafood_omega3_mg``.
    meal_kcal:
        Total energy of the whole meal in kcal (including non-risk foods). Used
        to displace the baseline diet by a factor
        ``f = (C_base - meal_kcal) / C_base``.
    country:
        ISO3 code. See :func:`list_countries`.
    mode:
        ``"population"`` (a): exact country-age-sex burden aggregation if the
        whole population substituted in the meal — a population-level *annual*
        YLL quantity. ``"median"`` (b) and ``"age"`` (c): individual
        *lifetime* quantities for the median adult / a person of the given
        ``age``, built from the life table.
    age:
        Required when ``mode="age"``; the person's current age in years,
        at least 25 (the lower bound of the bundled adult risk curves).
    include_processed_meat:
        Model processed meat as a separate harmful group (default True). When
        False the group is dropped from the model entirely, baseline included,
        and passing ``"processed_meat"`` in ``meal`` is an error.
    relative_only:
        If True, suppress absolute YLL and report only the relative metric
        (per-cause PAF). It uses the same sex-specific burden weights as the
        full result and therefore still requires bundled burden data.
    seafood_omega3_mg:
        Optional seafood-derived EPA + DHA in the meal, in milligrams. This is
        not total omega-3 and excludes plant ALA. ``None`` (the default) omits
        the factor from the assessment; ``0.0`` explicitly models a meal with
        no seafood omega-3 and therefore still displaces the country baseline.
    sodium_mg:
        Optional elemental sodium in the complete meal, in milligrams. Include
        sodium from ingredients, sauces, cooking salt, and table salt. ``None``
        omits sodium entirely; ``0.0`` explicitly models a sodium-free meal
        that displaces the country baseline. The sodium calculation uses a
        central country-age-sex mean-shift approximation through systolic blood
        pressure and does not model within-stratum exposure distributions.

    Returns
    -------
    MealAssessment
        Has ``delta_yll_local_total`` and ``delta_yll_standard_total`` (years
        gained if positive, lost if negative), a per-cause ``causes``
        breakdown, matching local and standard risk attribution, the
        substitution factor ``f``, and a ``summary()`` method.
        ``delta_yll_total`` and ``risk_attribution`` alias their local
        variants.
    """
    return assess(
        meal,
        meal_kcal,
        country,
        mode=mode,
        age=age,
        include_processed_meat=include_processed_meat,
        relative_only=relative_only,
        seafood_omega3_mg=seafood_omega3_mg,
        sodium_mg=sodium_mg,
    )


def per_meal_marginal(assessment: MealAssessment) -> float:
    """Linear/marginal per-meal attribution of a *lifetime* assessment.

    Returns ``delta_yll_local_total / MEALS_PER_LIFETIME``. Only meaningful for
    the individual lifetime modes (``"median"``/``"age"``). This is the
    lifetime effect divided evenly over the meals in a lifetime, NOT a
    biological single-meal effect.
    """
    if assessment.mode == "population":
        raise ValueError(
            "per_meal_marginal is defined for individual lifetime modes "
            "('median'/'age'), not the population-annual mode."
        )
    return assessment.delta_yll_local_total / MEALS_PER_LIFETIME


def list_countries() -> list[str]:
    """ISO3 codes with complete bundled data."""
    return data.available_countries()


def food_groups() -> dict[str, FoodGroup]:
    """The risk-factor food groups, with descriptions and required mass basis."""
    return dict(FOOD_GROUPS)


def nutrient_factors() -> dict[str, NutrientFactor]:
    """Optional nutrient factors, including API units and descriptions."""
    return dict(NUTRIENT_FACTORS)


__all__ = [
    "assess_meal",
    "per_meal_marginal",
    "list_countries",
    "food_groups",
    "nutrient_factors",
    "MealAssessment",
    "RISK_FACTORS",
    "CAUSE_LABELS",
]
