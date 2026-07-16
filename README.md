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
    sodium_mg=900,
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
* **Optional nutrient factors:** seafood omega-3 (EPA + DHA, excluding ALA)
  and elemental sodium, both supplied explicitly in mg per meal. Sodium is a
  labelled mean-shift prototype mediated through systolic blood pressure.
* **Diseases:** the food-group model covers coronary heart disease (CHD),
  ischemic stroke, type-2 diabetes (T2DM), and colorectal cancer (CRC). Sodium
  additionally covers stomach cancer, haemorrhagic stroke, and chronic kidney
  disease.
* **Age modes:**
  * `population` (a) — exact country × age × sex burden aggregation if the
    whole population ate the meal; a population-level **annual** YLL figure.
  * `median` (b) and `age` (c) — **individual lifetime** quantities for the
    median adult or a person of a given age, built from a life table and
    age/cause-specific death rates.
* **Relative-only output:** if you only want the relative metric (% change in
  diet-attributable risk, i.e. the PAF), pass `relative_only=True`. It retains
  the same burden weights and therefore still uses the bundled mortality,
  population, and life-table data.

## Installation

`mealhealth` installs straight from this Git repository (it is not on PyPI).
With **uv**:

```bash
uv add "mealhealth @ git+https://github.com/Sustainable-Solutions-Lab/mealhealth.git"
```

or add it to your project's `pyproject.toml`:

```toml
[project]
dependencies = [
    "mealhealth @ git+https://github.com/Sustainable-Solutions-Lab/mealhealth.git",
]
```

`pixi add --pypi "mealhealth @ git+..."` and plain
`pip install "git+https://github.com/..."` work too. Runtime dependencies are
just `numpy` and `pandas`; the data is bundled with the package. See the
[installation guide](https://sustainable-solutions-lab.github.io/mealhealth/installation.html)
for pinning to a tag, SSH URLs, and a local development checkout.

## Documentation

Full documentation is published at
**<https://sustainable-solutions-lab.github.io/mealhealth/>**. The sources live
in [`docs/`](docs/):

* [`docs/methodology.md`](docs/methodology.md) — the formulas, age modes, and
  substitution model.
* [`docs/food_groups.md`](docs/food_groups.md) — food-group definitions and the
  **mass basis** you must supply each group in (this matters for correctness).
* [`docs/data_sources.md`](docs/data_sources.md) — data provenance and
  **licensing** (read this before any redistribution or commercial use).
* [`docs/usage.md`](docs/usage.md) — API reference and worked examples.

Build the site locally with `uv run --group docs sphinx-build -b html docs docs/_build/html`.

## Licensing (important)

The **source code** is licensed **GPL-3.0-or-later**. However, the **bundled
data** carries a **non-commercial** restriction, which comes from IHME GBD; the
WHO mortality is governed separately by custom WHO dataset terms permitting
redistribution for public-health purposes with attribution. Other sources (UN
World Population Prospects and the GDD-IA dietary data) are more permissive —
GDD-IA is CC BY 4.0. The distributed package *as a whole* is therefore for
**non-commercial research, teaching and private study, with attribution** — the
GPL on the code does *not* grant unrestricted reuse of the bundled data. See
[`docs/data_sources.md`](docs/data_sources.md).

Repository: `git@github.com:Sustainable-Solutions-Lab/mealhealth.git`
