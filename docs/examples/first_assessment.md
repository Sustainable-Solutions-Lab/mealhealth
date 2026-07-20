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

# A first assessment

We start with one meal and read the result line by line.

```{code-cell} ipython3
:tags: [remove-output]

from mhstyle import GAIN, LOSS, apply_style, label_bars, sign_colors, zero_line
import matplotlib.pyplot as plt

import mealhealth as mh

apply_style()
```

Take a grain bowl: 250 g of vegetables, 100 g of whole grains (dry weight — see
[Food groups](../guide/food_groups.md#mass-basis-and-why-it-matters)), 80 g of
dry legumes, 550 kcal in total including the oil and the dressing that carry no
food-group mass of their own.

```{code-cell} ipython3
bowl = {"vegetables": 250, "whole_grains": 100, "legumes": 80}

result = mh.assess_meal(bowl, meal_kcal=550, country="USA", mode="median")
print(result.summary())
```

The headline is the first number: eating this bowl every day for the rest of
their life would gain the median American adult about half a year. Positive is a
gain, negative a loss.

Two versions of that figure are always reported. The **local** one weights each
averted death by remaining life expectancy from the USA's own life table; the
**GBD-standard** one uses GBD's aspirational reference table, which assigns more
remaining life at every age and so always gives the larger magnitude. Use local
for "years under current conditions", standard for comparison with published GBD
work.

Below the headline, `f = 0.788` says the meal displaces 21% of the day: 550 kcal
out of a US baseline of 2597.

## Where the years come from

Each cause contributes its own share. The population attributable fraction (PAF)
is the *relative* change in that cause's burden; the ΔYLL column is that fraction
weighted by how much burden the cause actually carries.

```{code-cell} ipython3
causes = [(mh.CAUSE_LABELS[c], r.paf_local, r.delta_yll_local)
          for c, r in result.causes.items()][::-1]  # report order, top down

fig, (ax_paf, ax_yll) = plt.subplots(1, 2, figsize=(9.5, 2.8), sharey=True)

labels = [c[0] for c in causes]
y = range(len(labels))

for ax, values, title, fmt in (
    (ax_paf, [c[1] for c in causes], "Relative change in burden (PAF)", "{:+.1%}"),
    (ax_yll, [c[2] for c in causes], "Years of life gained", "{:+.2f}"),
):
    bars = ax.barh(list(y), values, color=sign_colors(values), height=0.62)
    label_bars(ax, bars.patches, values, fmt=fmt)
    zero_line(ax)
    ax.set_title(title)
    ax.margins(x=0.3)
    ax.tick_params(length=0, labelbottom=False)
    ax.grid(axis="y", visible=False)
    ax.spines["bottom"].set_visible(False)

ax_paf.set_yticks(list(y), labels)
fig.suptitle("A grain bowl in the USA, median adult", x=0.005, ha="left",
             fontsize=12, weight="semibold")
fig.tight_layout()
```

The two panels do not agree on how much anything matters. Coronary heart disease
has a PAF one and a half times colorectal cancer's, but nearly eight times the
years — because it kills far more people to begin with. Ischemic stroke has more
than twice the PAF of type 2 diabetes and buys the same number of years.

A relative change and an absolute one answer different questions. Be explicit
about which you are quoting, especially when comparing against a study that
reports the other.

## Which foods did the work

`risk_attribution_local` splits the same total across risk factors, and the parts
sum to the whole.

```{code-cell} ipython3
attribution = dict(sorted(result.risk_attribution_local.items(),
                          key=lambda kv: kv[1]))

fig, ax = plt.subplots(figsize=(7.2, 3.4))
values = list(attribution.values())
bars = ax.barh(list(attribution), values, color=sign_colors(values), height=0.62)
label_bars(ax, bars.patches, values)
zero_line(ax)
ax.set_title("Contribution to the total, in years")
ax.margins(x=0.3)
ax.tick_params(length=0)
ax.grid(axis="y", visible=False)
fig.tight_layout()
```

Whole grains and legumes carry the gain, which is unsurprising. Fruit costing the
meal 0.05 years is the part that catches people out.

The bowl contains no fruit. But it displaces a fifth of the day's baseline diet,
and the American baseline does contain fruit, so some protective fruit intake
goes with it. By the same logic red meat and processed meat show up as small
*gains*: the meal displaces part of the baseline's meat without adding any of its
own.

Everything mealhealth reports is a comparison against the baseline diet. A meal
is never assessed in isolation — only against the share of the day it replaces.

```{code-cell} ipython3
:tags: [remove-input]

print(f"baseline diet, USA: {result.baseline_kcal:.0f} kcal/day")
for factor, grams in sorted(result.baseline_exposure.items()):
    print(f"  {factor:<16} {grams:6.1f} g/day")
```

## Next

[Comparing meals](comparing_meals.md) puts several meals side by side, which is
where the model is most useful and least prone to over-reading a single number.
