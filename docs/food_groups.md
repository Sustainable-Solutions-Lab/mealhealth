<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Food groups and mass basis

A meal is described to `mealhealth` as grams of each **risk-factor food group**
it contains, plus the meal's total energy. Only the groups below enter the
health calculation directly. Everything else in the meal (poultry, fish, eggs,
oils, refined/white grains, potatoes, sugar, dairy, …) affects the result only
through the meal's calorie total, by displacing the baseline diet.

## The seven risk-factor groups

| Group            | Harmful? | Diseases affected | Required input basis |
|------------------|:--------:|-------------------|----------------------|
| `fruits`         | no       | CHD, Stroke, T2DM | fresh weight (as eaten) |
| `vegetables`     | no       | CHD, Stroke       | fresh weight (as eaten) |
| `whole_grains`   | no       | CHD, Stroke, T2DM, CRC | **dry (uncooked) weight** |
| `legumes`        | no       | CHD               | **dry (uncooked) weight** |
| `nuts_seeds`     | no       | CHD, T2DM         | dry weight (as eaten) |
| `red_meat`       | yes      | CHD, Stroke, T2DM, CRC | fresh raw (retail) weight |
| `processed_meat` | yes      | CHD, T2DM, CRC    | fresh raw (retail) weight |

Definitions follow the GBD 2021 dietary risk-factor definitions.

## Mass basis — read this for correct numbers

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
* **Fresh raw retail weight** — `red_meat`, `processed_meat`: the raw weight as
  bought. Cooked meat ≈ 0.7 × raw (i.e. 100 g cooked ≈ 143 g raw).

### Red vs processed meat

`mealhealth` treats unprocessed and processed meat as **separate** groups, each
with its own dose–response curve and its own baseline exposure:

* `red_meat` — unprocessed beef, pork, lamb, goat.
* `processed_meat` — bacon, ham, sausages, hot dogs, deli/cured meats.

The per-country baseline split comes from the GDD-IA processed-meat fraction.
You can disable processed meat as a separate group with
`include_processed_meat=False`, in which case only the seven-minus-one groups
are modelled and any `processed_meat` you pass is rejected.

## Inspecting the definitions programmatically

```python
import mealhealth as mh
for name, fg in mh.food_groups().items():
    print(name, "|", fg.input_basis, "|", fg.description)
```
