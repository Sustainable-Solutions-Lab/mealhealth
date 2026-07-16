<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# mealhealth

`mealhealth` estimates how many **years of life you would lose or gain** if an
average person in a chosen country ate a given meal *every day for the rest of
their life*, relative to that country's current (baseline) diet. The metric is
built directly on **Global Burden of Disease (GBD)** relative-risk
dose–response curves for diet and chronic disease.

The meal is described in **food-group terms** (grams of vegetables, whole
grains, red meat, …), optional nutrient content, and total calories. It is
substituted into the baseline diet at **constant total calories**: the baseline
is scaled down to make caloric room for the meal, the meal exposures are added,
and the change in diet-attributable years of life lost (YLL) is computed.

```python
import mealhealth as mh

result = mh.assess_meal(
    meal={"vegetables": 250, "whole_grains": 100, "legumes": 80},
    meal_kcal=550,
    country="USA",
    seafood_omega3_mg=250,
    sodium_mg=900,
)
print(result.summary())
print("Total ΔYLL:", result.delta_yll_total)   # > 0 ⇒ years gained
print("By cause:", result.delta_paf_total)      # per-cause % risk change
```

## What it models

* **Food groups (GBD dietary risk factors):** fruits, vegetables, whole grains,
  legumes, nuts & seeds, unprocessed red meat, and **processed meat as a
  separate group**.
* **Optional nutrient factors:** seafood omega-3 (EPA + DHA, excluding ALA)
  and elemental sodium, both supplied explicitly in mg per meal. Sodium is a
  labelled country-age-sex mean-shift prototype mediated through systolic
  blood pressure.
* **Diseases:** the food-group model covers coronary heart disease (CHD),
  ischemic stroke, type-2 diabetes (T2DM), and colorectal cancer (CRC). Sodium
  additionally covers stomach cancer, haemorrhagic stroke, and chronic kidney
  disease.
* **Age modes:** a population-level annual YLL figure, or individual
  lifetime quantities for the median adult or a person of a given age.

## Where to go next

* **[Installation](installation.md)** — add `mealhealth` to a project (uv, pixi,
  `pyproject.toml`, pip) or set up a local development checkout.
* **[Usage](usage.md)** — the one function you need, worked examples, and the
  result object.
* **[Food groups](food_groups.md)** — group definitions and the **mass basis**
  you must supply each group in (this matters for correctness).
* **[Methodology](methodology.md)** — the substitution model, relative risk,
  PAF, the YLL anchor, and the age modes.
* **[Data sources](data_sources.md)** — provenance and **licensing** (read this
  before any redistribution or commercial use).
* **[API reference](api.md)** — the public functions and objects.

## Licensing at a glance

The **source code** is GPL-3.0-or-later, but the **bundled data** carries a
**non-commercial** restriction — it comes from IHME GBD. The other sources (UN
World Population Prospects, the GDD-IA dietary data (CC BY 4.0), NHANES) are
more permissive. WHO mortality is governed separately by custom WHO dataset
terms permitting redistribution for public-health purposes with attribution.
The distributed package *as a whole* is therefore for **non-commercial research,
teaching and private study, with attribution**. See
[Data sources](data_sources.md#licensing) for the details.

```{toctree}
:hidden:
:maxdepth: 2

installation
usage
food_groups
methodology
data_sources
api
```
