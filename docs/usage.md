<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Usage

## Install

```bash
uv pip install -e ".[dev]"   # or: pip install -e .
```

## The one function you need

```python
import mealhealth as mh

result = mh.assess_meal(
    meal={"vegetables": 250, "whole_grains": 100, "legumes": 80},
    meal_kcal=550,
    country="USA",
)
print(result.summary())
```

### `assess_meal(meal, meal_kcal, country, *, mode, age, include_processed_meat, relative_only)`

* `meal` — dict of risk-factor group → grams (in each group's required basis,
  see `docs/food_groups.md`). Keys must be in `mealhealth.RISK_FACTORS`.
* `meal_kcal` — total energy of the whole meal (kcal), including non-risk foods.
* `country` — ISO3 code; see `mealhealth.list_countries()` (175 countries).
* `mode` — `"population"` (default, annual population YLL), `"median"`
  (individual lifetime, median adult), or `"age"` (individual lifetime, needs
  `age=`).
* `age` — required for `mode="age"`: the person's current age in years.
* `include_processed_meat` — model processed meat separately (default `True`).
* `relative_only` — report only per-cause PAF, skip the YLL anchor.

### The result object

```python
result.delta_yll_total      # net ΔYLL (years gained if > 0, lost if < 0)
result.causes               # dict cause -> CauseResult(paf, delta_yll, rr_*)
result.delta_paf_total      # dict cause -> PAF (relative metric)
result.risk_attribution     # dict food group -> ΔYLL attributed (sums to total)
result.f                    # baseline scaling factor used
result.exposure             # substituted-diet exposures per group
result.warnings             # e.g. meal exceeds baseline calories
result.summary()            # human-readable report
```

## Examples

### Population vs individual

```python
meal = {"red_meat": 150, "processed_meat": 60}

pop = mh.assess_meal(meal, 650, "USA")                       # annual, whole pop
ind = mh.assess_meal(meal, 650, "USA", mode="age", age=45)   # per-person lifetime
print(pop.delta_yll_total, ind.delta_yll_total)
print("per-meal marginal (years):", mh.per_meal_marginal(ind))
```

### Relative-only metric (no burden data)

```python
r = mh.assess_meal({"vegetables": 300}, 200, "FRA", relative_only=True)
print(r.delta_paf_total)   # {'CHD': +0.07, 'Stroke': +0.04, ...}
```

### Inspecting food groups and countries

```python
mh.list_countries()                  # ['AFG', 'AGO', ..., 'ZWE']
mh.food_groups()["whole_grains"].input_basis   # 'dry weight (uncooked)'
```

## Reproducing the bundled data

The bundled CSVs are derived from the `food-opt` project. To regenerate them
(requires licensed copies of the GBD/GDD raw data, present in a `food-opt`
checkout):

```bash
cd /path/to/food-opt
.pixi/envs/default/bin/python /path/to/meal-health-indicator/tools/prepare_data.py
```
