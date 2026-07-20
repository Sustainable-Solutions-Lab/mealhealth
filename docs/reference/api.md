<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# API reference

Everything below is importable directly from the top-level `mealhealth`
package. For narrative usage and worked examples, see [Quickstart](../guide/quickstart.md).

```{eval-rst}
.. currentmodule:: mealhealth
```

## Functions

```{eval-rst}
.. autofunction:: assess_meal
.. autofunction:: per_meal_marginal
.. autofunction:: list_countries
.. autofunction:: food_groups
.. autofunction:: nutrient_factors
```

## Result and definition objects

```{eval-rst}
.. autoclass:: MealAssessment
   :members:
   :undoc-members:

.. autoclass:: FoodGroup
   :members:
   :undoc-members:

.. autoclass:: NutrientFactor
   :members:
   :undoc-members:
```

## Constants

`mealhealth.RISK_FACTORS`
: Tuple of the valid food-group keys accepted in the `meal` argument of
  {py:func}`~mealhealth.assess_meal`: `fruits`, `vegetables`, `whole_grains`,
  `legumes`, `nuts_seeds`, `red_meat`, `processed_meat`.

`mealhealth.MODEL_RISK_FACTORS`
: Every risk factor the engine can evaluate — the seven food groups above plus
  the two optional nutrient factors `omega3` and `sodium`. These are the keys
  that can appear in `exposure`, `baseline_exposure`, and the risk-attribution
  dictionaries of a {py:class}`~mealhealth.MealAssessment`. Nutrient factors are
  not accepted in `meal`; they have their own keyword arguments.

`mealhealth.CAUSES`
: Tuple of the modelled disease causes, in report order: `CHD`, `Stroke`,
  `T2DM`, `CRC`, `StomachCancer`, `HaemorrhagicStroke`, `CKD`. The last three
  are reachable only through sodium, so they appear in a result only when
  `sodium_mg` is supplied.

`mealhealth.CAUSE_LABELS`
: Dict mapping each cause code in `CAUSES` to its human-readable label — for
  example `CHD` → "Coronary (ischemic) heart disease" and
  `HaemorrhagicStroke` → "Haemorrhagic stroke".

`mealhealth.FOOD_GROUPS`, `mealhealth.NUTRIENT_FACTORS`
: The underlying definition mappings returned (as copies) by
  {py:func}`~mealhealth.food_groups` and
  {py:func}`~mealhealth.nutrient_factors`. Prefer the functions; these are
  exported for callers that want the shared immutable objects.

`mealhealth.__version__`
: Package version string.
