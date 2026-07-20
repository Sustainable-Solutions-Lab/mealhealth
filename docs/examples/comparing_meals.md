---
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: CC-BY-4.0
jupytext:
  text_representation:
    extension: .md
    format_name: myst
    format_version: 0.13
kernelspec:
  display_name: Python 3
  language: python
  name: python3
---

# Comparing meals

A single ΔYLL figure carries more precision than the model can honestly
support. A ranking of several meals, computed the same way against the same
baseline, is much sturdier — the shared assumptions cancel.

```{code-cell} ipython3
:tags: [remove-output]

from mhstyle import (NEUTRAL, SERIES, apply_style, label_bars, sign_colors,
                     zero_line)
import matplotlib.pyplot as plt

import mealhealth as mh

apply_style()
```

Six meals, each described in food-group grams plus total energy. Anything
outside the risk groups — the chicken, the oil, the bread's refined share, the
chips — is not listed; it enters only through the calorie total, by displacing
baseline diet.

```{code-cell} ipython3
MEALS = {
    "Grain bowl": (dict(vegetables=250, whole_grains=100, legumes=80), 550, {}),
    "Salmon and greens": (dict(vegetables=220, whole_grains=60), 600,
                          dict(seafood_omega3_mg=1400)),
    "Chicken sandwich": (dict(whole_grains=60), 620, dict(sodium_mg=1100)),
    "Lentil stew": (dict(legumes=120, vegetables=200), 520, {}),
    "Full English": (dict(processed_meat=120, red_meat=40), 850,
                     dict(sodium_mg=2000)),
    "Cheeseburger and fries": (dict(red_meat=150, processed_meat=30), 900,
                               dict(sodium_mg=1500)),
}

results = {
    name: mh.assess_meal(meal, kcal, "USA", mode="median", **extra)
    for name, (meal, kcal, extra) in MEALS.items()
}

ranked = sorted(results.items(), key=lambda kv: kv[1].delta_yll_local_total)
for name, r in reversed(ranked):
    print(f"{name:<24}{r.delta_yll_local_total:+.2f} years")
```

## The ranking

```{code-cell} ipython3
names = [name for name, _ in ranked]
values = [r.delta_yll_local_total for _, r in ranked]

fig, ax = plt.subplots(figsize=(7.2, 3.6))
bars = ax.barh(names, values, color=sign_colors(values), height=0.62)
label_bars(ax, bars.patches, values)
zero_line(ax)
ax.set_title("Years of life gained or lost, eaten daily\nUSA, median adult, local life table")
ax.set_xlabel("Δ years of life")
ax.margins(x=0.22)
ax.tick_params(length=0)
ax.grid(axis="y", visible=False)
fig.tight_layout()
```

The spread runs from about +0.56 years to −0.94, a range of one and a half
years of life depending on what you eat every day. The ordering is not
surprising, which is the point: a model that ranked the full English above the
lentil stew would be telling us something is wrong.

The chicken sandwich is the interesting one. It contains barely any risk-group
food — 60 g of whole grains and a lot of sodium — and still comes out positive,
because at 620 kcal it displaces a quarter of the American baseline diet,
including that quarter's red and processed meat. A meal can score well by what
it crowds out rather than by what it contains.

## What is driving each result

The same total, split by risk factor. Reading down a column shows which foods
made a meal good or bad; reading across a row shows how consistently one factor
matters.

```{code-cell} ipython3
ORDER = ["whole_grains", "legumes", "vegetables", "fruits", "red_meat",
         "processed_meat", "omega3", "sodium", "nuts_seeds"]

contributions = {
    factor: [results[name].risk_attribution_local.get(factor, 0.0)
             for name in names]
    for factor in ORDER
}
# The palette has eight slots, assigned in fixed order and never cycled, so
# anything past the eighth largest factor folds into "other" rather than
# reusing a colour that already means something else.
by_size = sorted(contributions, key=lambda f: max(map(abs, contributions[f])),
                 reverse=True)
keep = [f for f in ORDER if f in by_size[:len(SERIES)]]
fold = [f for f in ORDER if f not in keep]

active = {f.replace("_", " "): contributions[f] for f in keep}
if fold:
    active["other"] = [sum(contributions[f][i] for f in fold)
                       for i in range(len(names))]
    print("folded into 'other':", ", ".join(fold))

colors = dict(zip(active, SERIES, strict=False))
if fold:
    colors["other"] = NEUTRAL

fig, ax = plt.subplots(figsize=(8.0, 4.6))
positive = [0.0] * len(names)
negative = [0.0] * len(names)

for factor, values_ in active.items():
    base = [positive[i] if c >= 0 else negative[i] for i, c in enumerate(values_)]
    ax.barh(names, values_, left=base, height=0.6, color=colors[factor],
            label=factor, edgecolor="#fcfcfb", linewidth=1.2)
    for i, c in enumerate(values_):
        if c >= 0:
            positive[i] += c
        else:
            negative[i] += c

zero_line(ax)
ax.set_title("Contribution of each risk factor, in years")
ax.tick_params(length=0)
ax.grid(axis="y", visible=False)
ax.legend(ncols=4, loc="upper center", bbox_to_anchor=(0.5, -0.06),
          columnspacing=1.4, handlelength=1.1)
fig.tight_layout()
```

Sodium is visible but small next to the food groups, and it is the one factor
here carrying no uncertainty interval at all — see
[Limitations](../model/limitations.md#sodium-is-a-mean-shift-approximation)
before leaning on it.

Note that every meal shows a *negative* fruit contribution, including the good
ones. None of these six meals contains fruit, and all of them displace part of a
baseline diet that does.

## Relative rather than absolute

If the absolute YLL anchor is not what you want — for a comparison where only
the ordering matters — `relative_only=True` reports the per-cause PAFs and
suppresses the years.

```{code-cell} ipython3
rel = mh.assess_meal(MEALS["Grain bowl"][0], 550, "USA", relative_only=True)
{cause: round(paf, 4) for cause, paf in rel.delta_paf_total.items()}
```

This still uses the bundled mortality and population data, because the PAFs are
burden-weighted across age and sex. It suppresses the years; it does not make
the result independent of the burden inputs.

## Next

[The same meal across countries](across_countries.md) holds the meal fixed and
varies the baseline instead.
