# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Public API for the meal health indicator."""

from __future__ import annotations

from . import data
from .foodgroups import CAUSE_LABELS, FOOD_GROUPS, RISK_FACTORS, FoodGroup
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
) -> MealAssessment:
    """Assess the health impact of eating ``meal`` every day in ``country``.

    Parameters
    ----------
    meal:
        Mapping of risk-factor food group -> grams in the meal, each in the
        group's required input basis (see :func:`food_groups`). Valid keys are
        the entries of :data:`mealhealth.RISK_FACTORS`. Foods outside these
        groups (poultry, fish, eggs, oils, refined grains, ...) are not listed
        here; they enter only through ``meal_kcal``.
    meal_kcal:
        Total energy of the whole meal in kcal (including non-risk foods). Used
        to displace the baseline diet by a factor
        ``f = (C_base - meal_kcal) / C_base``.
    country:
        ISO3 code. See :func:`list_countries`.
    mode:
        ``"population"`` (a): age(YLL)-weighted effective impact if the whole
        population substituted in the meal — a population-level *annual* YLL
        quantity. ``"median"`` (b) and ``"age"`` (c): individual *lifetime*
        quantities for the median adult / a person of the given ``age``, built
        from the life table.
    age:
        Required when ``mode="age"``; the person's current age in years.
    include_processed_meat:
        Model processed meat as a separate harmful group (default True).
    relative_only:
        If True, skip the absolute-YLL anchor and report only the relative
        metric (per-cause PAF: the % change in diet-attributable risk). This is
        the degraded fallback that needs only RR curves + baseline exposure.

    Returns
    -------
    MealAssessment
        Has ``delta_yll_total`` (years gained if positive, lost if negative),
        a per-cause ``causes`` breakdown, ``risk_attribution`` per food group,
        the substitution factor ``f``, and a ``summary()`` method.
    """
    return assess(
        meal,
        meal_kcal,
        country,
        mode=mode,
        age=age,
        include_processed_meat=include_processed_meat,
        relative_only=relative_only,
    )


def per_meal_marginal(assessment: MealAssessment) -> float:
    """Linear/marginal per-meal attribution of a *lifetime* assessment.

    Returns ``delta_yll_total / MEALS_PER_LIFETIME``. Only meaningful for the
    individual lifetime modes (``"median"``/``"age"``). This is the lifetime
    effect divided evenly over the meals in a lifetime, NOT a biological
    single-meal effect.
    """
    if assessment.mode == "population":
        raise ValueError(
            "per_meal_marginal is defined for individual lifetime modes "
            "('median'/'age'), not the population-annual mode."
        )
    return assessment.delta_yll_total / MEALS_PER_LIFETIME


def list_countries() -> list[str]:
    """ISO3 codes with complete bundled data."""
    return data.available_countries()


def food_groups() -> dict[str, FoodGroup]:
    """The risk-factor food groups, with descriptions and required mass basis."""
    return dict(FOOD_GROUPS)


__all__ = [
    "assess_meal",
    "per_meal_marginal",
    "list_countries",
    "food_groups",
    "MealAssessment",
    "RISK_FACTORS",
    "CAUSE_LABELS",
]
