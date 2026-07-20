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

# Age

The same daily meal is worth more to a 30-year-old than to an 80-year-old, for
two reasons that the model keeps separate.

```{code-cell} ipython3
:tags: [remove-output]

from mhstyle import GAIN, LOSS, SERIES, apply_style, zero_line
import matplotlib.pyplot as plt
import numpy as np

import mealhealth as mh

apply_style()
```

`mode="age"` takes the person's current age. It starts at 25, the lower bound of
the bundled adult risk curves.

```{code-cell} ipython3
ages = np.arange(25, 91, 2.5)
bowl = {"vegetables": 250, "whole_grains": 100, "legumes": 80}
burger = {"red_meat": 150, "processed_meat": 30}

series = {
    "Grain bowl": [mh.assess_meal(bowl, 550, "USA", mode="age", age=float(a))
                   .delta_yll_local_total for a in ages],
    "Cheeseburger": [mh.assess_meal(burger, 900, "USA", mode="age", age=float(a),
                                    sodium_mg=1500).delta_yll_local_total
                     for a in ages],
}
```

```{code-cell} ipython3
fig, ax = plt.subplots(figsize=(7.2, 4.0))

for (label, values), color in zip(series.items(), (GAIN, LOSS), strict=True):
    ax.plot(ages, values, color=color)
    ax.annotate(label, (ages[-1], values[-1]), xytext=(6, 0),
                textcoords="offset points", va="center", fontsize=9,
                color=color)

zero_line(ax, vertical=False)
ax.set_title("Lifetime effect of eating this daily, by age when you start")
ax.set_xlabel("age (years)")
ax.set_ylabel("Δ remaining-lifetime years of life")
ax.set_xlim(25, 100)
ax.tick_params(length=0)
fig.tight_layout()
```

Both curves shrink with age without reaching zero. The grain bowl is worth
0.60 years to a 25-year-old and 0.35 to an 80-year-old — still well over half
as much. "It is too late to bother" is not what the arithmetic says, and the
decline is gentler through middle age than most people expect: two-thirds of
the value at 25 survives to 65.

## Two mechanisms, separated

The decline combines a shrinking risk effect with shrinking remaining life.
Comparing against the population attributable fraction — which carries no life
expectancy at all — separates them.

```{code-cell} ipython3
paf = [mh.assess_meal(bowl, 550, "USA", mode="age", age=float(a))
       .causes["CHD"].paf_local for a in ages]
yll = series["Grain bowl"]

fig, (ax_paf, ax_yll) = plt.subplots(1, 2, figsize=(8.6, 3.4))

ax_paf.plot(ages, np.array(paf) * 100, color=SERIES[1])
ax_paf.set_title("Risk effect alone (CHD PAF)")
ax_paf.set_ylabel("% of CHD burden removed")

ax_yll.plot(ages, yll, color=GAIN)
ax_yll.set_title("Risk effect × remaining life")
ax_yll.set_ylabel("Δ years of life")

for ax in (ax_paf, ax_yll):
    ax.set_xlabel("age (years)")
    ax.set_ylim(bottom=0)
    ax.tick_params(length=0)

fig.tight_layout()
```

The left panel is a staircase because the risk curves are defined on five-year
age bands, not as a smooth function of age. It falls because the bundled curves
attenuate — the same intake change moves risk less in an older person, a shape
taken from the GBD 2019 relative-risk workbook — and it flattens above 75, where
the attenuation table stops changing.

The right panel multiplies that by remaining life, which keeps falling, and so
the product declines even where the PAF has levelled off. Two mechanisms,
different shapes, and only their product is what you would quote.

## The median adult

`mode="median"` picks the population-weighted median adult age rather than
making you choose one.

```{code-cell} ipython3
median = mh.assess_meal(bowl, 550, "USA", mode="median")
print(f"median adult: {median.delta_yll_local_total:+.3f} years")
print(f"per meal:     {mh.per_meal_marginal(median) * 365 * 24 * 60:+.1f} minutes")
```

The per-meal figure divides the lifetime effect evenly over a nominal
lifetime's meals. It is an accounting convention that communicates scale well
and means nothing biologically — the model has no notion of a single meal's
effect on a body. Quote it with that caveat attached, and note that it is
undefined in population mode.

## Next

[Sodium](sodium.md) covers the one factor with a mediated pathway.
