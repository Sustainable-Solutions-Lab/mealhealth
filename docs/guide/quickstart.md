<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Quickstart

See [Installation](installation.md) for how to add `mealhealth` to a project.
Once a meal is assessed, [Interpreting results](interpreting.md) explains what
the numbers mean.

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

### `assess_meal(meal, meal_kcal, country, *, mode, age, include_processed_meat, relative_only, seafood_omega3_mg, sodium_mg)`

* `meal` — dict of risk-factor group → grams, each in the group's required basis
  (see [Food groups](food_groups.md)). Keys must be in `mealhealth.RISK_FACTORS`.
* `meal_kcal` — total energy of the whole meal (kcal), including non-risk foods.
* `country` — ISO3 code; see `mealhealth.list_countries()` (175 countries).
* `mode` — `"population"` (default, annual population YLL), `"median"`
  (individual lifetime, median adult), or `"age"` (individual lifetime, needs
  `age=`).
* `age` — required for `mode="age"`: the person's current age in years. It
  must be at least 25, the lower bound of the bundled adult risk curves.
* `include_processed_meat` — model processed meat separately (default `True`).
* `relative_only` — report only per-cause PAF and suppress YLL values. The PAF
  retains the same burden weighting, so this does not remove the bundled
  mortality, population, or life-table dependency.
* `seafood_omega3_mg` — optional seafood EPA + DHA in mg per meal (not total
  omega-3; excludes ALA). Omit/`None` to exclude this factor; pass `0.0` to state
  that the meal contains none while still modelling displacement of baseline
  seafood omega-3.
* `sodium_mg` — optional **elemental sodium** in the complete meal, in mg.
  Include ingredients, sauces, cooking salt, and table salt. Omit/`None` to
  exclude sodium; pass `0.0` to model a measured sodium-free meal that still
  displaces baseline sodium. The sodium calculation is a central mean-shift
  approximation, not an individualized blood-pressure prediction.

### The result object

```python
result.delta_yll_local_total # net ΔYLL using the country's life table
result.delta_yll_total       # alias for delta_yll_local_total
result.delta_yll_standard_total # potential ΔYLL using the GBD reference table
result.causes               # cause -> CauseResult with local/standard PAF/YLL/RR
result.delta_paf_local_total # dict cause -> local-weighted PAF
result.delta_paf_standard_total # dict cause -> standard-weighted PAF
result.delta_paf_total       # alias for delta_paf_local_total
result.risk_attribution_local # active factor -> local ΔYLL (sums to local total)
result.risk_attribution       # alias for risk_attribution_local
result.risk_attribution_standard # same decomposition for GBD-standard ΔYLL
result.f                    # baseline scaling factor used
result.exposure             # substituted-diet exposures per group
result.warnings             # e.g. meal exceeds baseline calories
result.summary()            # human-readable report
```

When supplied, `omega3` or `sodium` appears in `exposure`,
`baseline_exposure`, and the attribution dictionaries. Omega-3 exposure is in
g/day. Sodium exposure is the adult-population-weighted mean **24-hour urinary
sodium** in g/day, after converting the meal's dietary sodium input.

## Examples

### Population vs individual

```python
meal = {"red_meat": 150, "processed_meat": 60}

pop = mh.assess_meal(meal, 650, "USA")                       # annual, whole pop
ind = mh.assess_meal(meal, 650, "USA", mode="age", age=45)   # per-person lifetime
print(pop.delta_yll_local_total, ind.delta_yll_local_total)
print(pop.delta_yll_standard_total, ind.delta_yll_standard_total)
print("per-meal marginal (years):", mh.per_meal_marginal(ind))
```

### Relative-only metric

```python
r = mh.assess_meal({"vegetables": 300}, 200, "FRA", relative_only=True)
print(r.delta_paf_total)   # {'CHD': +0.07, 'Stroke': +0.04, ...}
```

### Seafood omega-3

```python
salmon = mh.assess_meal(
    meal={"vegetables": 150},
    meal_kcal=600,
    country="USA",
    seafood_omega3_mg=1200,  # EPA + DHA from the whole meal
)
print(salmon.causes["CHD"].paf)
```

### Sodium

```python
meal = mh.assess_meal(
    meal={"vegetables": 180, "whole_grains": 70},
    meal_kcal=650,
    country="USA",
    sodium_mg=900,  # elemental sodium from the complete meal
)
print(meal.risk_attribution_local["sodium"])
print(meal.causes["CHD"].paf_local)
print(meal.warnings)  # records the central mean-shift approximation
```

If only salt mass is known, an approximate conversion is
`sodium_mg = salt_g * 1000 / 2.542`. Do not pass salt mass directly.

### Inspecting food groups and countries

```python
mh.list_countries()                  # ['AFG', 'AGO', ..., 'ZWE']
mh.food_groups()["whole_grains"].input_basis   # 'dry weight (uncooked)'
mh.nutrient_factors()["omega3"].api_unit       # 'mg'
mh.nutrient_factors()["sodium"].api_unit       # 'mg'
```

## Next

The [examples](../examples/index.md) take the same API into comparisons across
meals, countries, intakes and ages, with plots.
[Interpreting results](interpreting.md) covers what the numbers mean and how far
to trust them, and [Troubleshooting](troubleshooting.md) covers the errors and
warnings you are most likely to hit.
