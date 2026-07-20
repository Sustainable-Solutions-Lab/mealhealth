<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Food groups and mass basis

A meal is described to `mealhealth` as grams of each **risk-factor food group**
it contains, plus the meal's total energy. Only the groups below enter the
health calculation directly. Everything else in the meal (poultry, eggs, oils,
refined/white grains, potatoes, sugar, dairy, …) affects the result only through
the meal's calorie total, by displacing the baseline diet. Fish and shellfish
also contribute when their EPA+DHA content is supplied through the optional
nutrient input below. Sodium is likewise supplied as a nutrient amount, not as
food-group mass.

## The seven risk-factor groups

| Group            | Harmful? | Diseases affected | Required input basis |
|------------------|:--------:|-------------------|----------------------|
| `fruits`         | no       | CHD, Stroke, T2DM | fresh weight (as eaten) |
| `vegetables`     | no       | CHD, Stroke       | fresh weight (as eaten) |
| `whole_grains`   | no       | CHD, Stroke, T2DM, CRC | **dry (uncooked) weight** |
| `legumes`        | no       | CHD               | **dry (uncooked) weight** |
| `nuts_seeds`     | no       | CHD               | dry weight (as eaten) |
| `red_meat`       | yes      | CHD, Stroke, T2DM, CRC | fresh raw (retail) weight |
| `processed_meat` | yes      | CHD, T2DM, CRC    | as-eaten product weight |

Definitions follow the GBD dietary risk-factor definitions.

## Nutrient inputs

Seafood omega-3 is not another food-group mass. Pass its nutrient content
separately as `seafood_omega3_mg=` in **mg per meal**. It means the combined
long-chain seafood fatty acids EPA + DHA and excludes plant omega-3 ALA. The
model converts mg to its internal g/day exposure axis and applies the GBD
seafood-omega-3 → CHD curve.

The argument is optional because callers may not know a meal's nutrient
composition. Omitted or `None` means “do not assess this factor”; `0.0` means
“the meal contains no EPA+DHA.” The latter still scales down the country's
nonzero baseline exposure and can therefore produce a CHD penalty. Oily-fish
servings commonly contain hundreds to more than 1,000 mg EPA+DHA, while lean
seafood can contain much less; use a nutrition database or product analysis for
the actual meal rather than estimating from seafood mass alone.

Sodium is supplied separately as `sodium_mg=` in **mg of elemental sodium per
meal**. Include sodium naturally present in ingredients plus sauces, cooking
salt, and salt added at the table. This is not the mass of sodium chloride:
when only salt mass is known, use the approximate conversion
`sodium_mg = salt_g * 1000 / 2.542`.

As with omega-3, omitted/`None` means “do not assess sodium,” whereas `0.0`
means a measured sodium-free meal and still displaces the country baseline.
The model converts dietary sodium to the GBD 24-hour urinary-sodium basis and
evaluates a country × age × sex mean SBP shift. It does not use personal blood
pressure, hypertension treatment, kidney function, or salt sensitivity.

## Mass basis, and why it matters

The relative-risk curves and the bundled baseline diet are all expressed in a
consistent per-group **basis** (GBD's native exposure bases reconciled with
measured intakes). You must supply each meal group's mass in the **same
basis**, or the numbers will be off:

* **Fresh / as-eaten weight** — `fruits`, `vegetables`, `nuts_seeds`: the
  weight of the food ready to eat (a raw apple, a portion of cooked
  vegetables, a handful of almonds).
* **Dry / uncooked weight** — `whole_grains`, `legumes`: the weight *before*
  cooking, because that is how GBD defines whole-grain and legume exposure.
  Rough conversions if you only know the cooked weight: cooked grains ≈ 0.45 ×
  dry, cooked legumes ≈ 0.40 × dry (i.e. 150 g cooked brown rice ≈ 67 g dry;
  130 g cooked lentils ≈ 52 g dry).
* **Fresh raw retail weight** — `red_meat`: the raw weight as bought. Cooked
  meat ≈ 0.7 × raw (i.e. 100 g cooked ≈ 143 g raw).
* **As-eaten product weight** — `processed_meat`: the product weight supplied
  to the meal (for example, the stated weight of bacon, ham, or sausage).

### Red vs processed meat

`mealhealth` treats unprocessed and processed meat as **separate** groups, each
with its own dose–response curve and its own baseline exposure:

* `red_meat` — unprocessed beef, pork, lamb, goat.
* `processed_meat` — bacon, ham, sausages, hot dogs, deli/cured meats.

The per-country baseline rows come directly from the GBD 2023 processed-meat
and red-meat exposure files (see [Data sources](../model/data_sources.md#baseline-exposure)).
You can disable processed meat as a separate group with
`include_processed_meat=False`. That drops the group from the model entirely —
the country's baseline processed-meat intake goes too, not just the meal's — so
only the remaining six groups are assessed. Passing `processed_meat` in the meal
alongside the flag raises `ValueError` rather than silently discarding it.

## Inspecting the definitions programmatically

```python
import mealhealth as mh
for name, fg in mh.food_groups().items():
    print(name, "|", fg.input_basis, "|", fg.description)
```
