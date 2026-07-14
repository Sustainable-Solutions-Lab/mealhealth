<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# mealhealth — a healthiness metric for a meal

`mealhealth` estimates how many **years of life you would lose or gain** if an
average person in a chosen country ate a given meal *every day for the rest of
their life*, relative to that country's current (baseline) diet. The metric is
built directly on **Global Burden of Disease (GBD)** relative-risk
dose–response curves for diet and chronic disease.

The meal is described in **food-group terms** (grams of vegetables, whole
grains, red meat, …), optional nutrient content, and total calories. The meal is
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
)
print(result.summary())
print("Local ΔYLL:", result.delta_yll_local_total)  # > 0 ⇒ years gained
print("GBD-standard ΔYLL:", result.delta_yll_standard_total)
print("By cause:", result.delta_paf_total)            # per-cause % risk change
```

## What it models

* **Food groups (GBD dietary risk factors):** fruits, vegetables, whole grains,
  legumes, nuts & seeds, unprocessed red meat, and **processed meat as a
  separate group**.
* **Optional nutrient factor:** seafood omega-3 (EPA + DHA, excluding ALA),
  supplied explicitly in mg per meal and linked to CHD.
* **Diseases:** coronary heart disease (CHD), ischemic stroke, type-2 diabetes
  (T2DM), colorectal cancer (CRC), each acting on its GBD-mapped causes
  (processed meat: CHD, T2DM, CRC).
* **Age modes:**
  * `population` (a) — age-(YLL-)weighted effective impact if the whole
    population ate the meal; a population-level **annual** YLL figure.
  * `median` (b) and `age` (c) — **individual lifetime** quantities for the
    median adult or a person of a given age, built from a life table and
    age/cause-specific death rates.
* **Relative-only fallback:** if you only want the relative metric (% change in
  diet-attributable risk, i.e. the PAF), pass `relative_only=True`; this needs
  only the RR curves and baseline exposure, not the mortality/life-table data.

## Installation

```bash
pip install -e .          # or: uv pip install -e ".[dev]"
```

Runtime dependencies are just `numpy` and `pandas`. Data needed for the
calculation is bundled with the package.

## Documentation

* [`docs/methodology.md`](docs/methodology.md) — the formulas, age modes, and
  substitution model.
* [`docs/food_groups.md`](docs/food_groups.md) — food-group definitions and the
  **mass basis** you must supply each group in (this matters for correctness).
* [`docs/data_sources.md`](docs/data_sources.md) — data provenance and
  **licensing** (read this before any redistribution or commercial use).
* [`docs/usage.md`](docs/usage.md) — API reference and worked examples.

## Licensing (important)

The **source code** is licensed **GPL-3.0-or-later**. However, the **bundled
data** is derived from GBD, the Global Dietary Database (GDD-IA) and UN World
Population Prospects, which carry **non-commercial** terms. The distributed
package *as a whole* is therefore for **non-commercial research, teaching and
private study only** — the GPL on the code does *not* grant unrestricted reuse
of the bundled data. See [`docs/data_sources.md`](docs/data_sources.md).

Repository: `git@github.com:Sustainable-Solutions-Lab/mealhealth.git`
