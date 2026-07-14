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

### `assess_meal(meal, meal_kcal, country, *, mode, age, include_processed_meat, relative_only, seafood_omega3_mg)`

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
* `seafood_omega3_mg` — optional seafood EPA + DHA in mg per meal (not total
  omega-3; excludes ALA). Omit/`None` to exclude this factor; pass `0.0` to state
  that the meal contains none while still modelling displacement of baseline
  seafood omega-3.

### The result object

```python
result.delta_yll_total      # net ΔYLL using the country's life table
result.delta_yll_local_total # explicit alias for delta_yll_total
result.delta_yll_standard_total # potential ΔYLL using the GBD reference table
result.causes               # dict cause -> CauseResult(paf, delta_yll, rr_*)
result.delta_paf_total      # dict cause -> PAF (relative metric)
result.risk_attribution     # dict active risk factor -> ΔYLL (sums to total)
result.risk_attribution_standard # same decomposition for GBD-standard ΔYLL
result.f                    # baseline scaling factor used
result.exposure             # substituted-diet exposures per group
result.warnings             # e.g. meal exceeds baseline calories
result.summary()            # human-readable report
```

When supplied, `omega3` appears as an additional key in `exposure`,
`baseline_exposure`, and `risk_attribution`; those exposure dictionaries use the
engine's internal g/day unit.

## Examples

### Population vs individual

```python
meal = {"red_meat": 150, "processed_meat": 60}

pop = mh.assess_meal(meal, 650, "USA")                       # annual, whole pop
ind = mh.assess_meal(meal, 650, "USA", mode="age", age=45)   # per-person lifetime
print(pop.delta_yll_total, ind.delta_yll_total)
print(pop.delta_yll_standard_total, ind.delta_yll_standard_total)
print("per-meal marginal (years):", mh.per_meal_marginal(ind))
```

### Relative-only metric (no burden data)

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

### Inspecting food groups and countries

```python
mh.list_countries()                  # ['AFG', 'AGO', ..., 'ZWE']
mh.food_groups()["whole_grains"].input_basis   # 'dry weight (uncooked)'
mh.nutrient_factors()["omega3"].api_unit       # 'mg'
```

## Reproducing the bundled data

The bundled **health and demographic** CSVs (`relative_risks.csv`,
`mortality.csv`, `population.csv`, `life_table.csv`) are regenerated from public
source datasets. Download the two IHME GBD files into `data/raw/` (the UN WPP
files download automatically), then run:

```bash
python tools/prepare_data.py
```

See [`data_sources.md`](data_sources.md) for exactly which files to download and
where to place them. The **baseline diet** (`baseline_intake.csv`,
`baseline_calories.csv`) is a separate bundled dataset and is not built by this
tool — see the "Baseline diet" section of that document.
