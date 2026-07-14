<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# API reference

Everything below is importable directly from the top-level `mealhealth`
package. For narrative usage and worked examples, see [Usage](usage.md).

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

`mealhealth.CAUSE_LABELS`
: Dict mapping each modelled disease cause code to its human-readable label —
  `CHD` → "Coronary (ischemic) heart disease", `Stroke` → "Ischemic stroke",
  `T2DM` → "Type 2 diabetes mellitus", `CRC` → "Colorectal cancer".
