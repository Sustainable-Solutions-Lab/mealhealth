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

# Dose and response

Sweeping one food group from nothing to a lot makes two things visible that a
single assessment hides: the curves are not straight, and they stop.

```{code-cell} ipython3
:tags: [remove-output]

from mhstyle import GAIN, LOSS, SERIES, apply_style, zero_line
import matplotlib.pyplot as plt
import numpy as np

import mealhealth as mh

apply_style()
```

## One group at a time

Hold calories fixed at 600 kcal so the displacement of the baseline diet is the
same at every point, and vary only the grams of one group.

```{code-cell} ipython3
grams = np.arange(0, 401, 10)

def sweep(group, **extra):
    return [
        mh.assess_meal({group: float(g)}, 600, "USA", mode="median",
                       **extra).delta_yll_local_total
        for g in grams
    ]

curves = {group: sweep(group) for group in
          ["vegetables", "whole_grains", "legumes", "red_meat",
           "processed_meat"]}
```

```{code-cell} ipython3
fig, ax = plt.subplots(figsize=(7.6, 4.4))

for (group, values), color in zip(curves.items(), SERIES, strict=False):
    ax.plot(grams, values, color=color, label=group.replace("_", " "))
    ax.annotate(group.replace("_", " "), (grams[-1], values[-1]),
                xytext=(6, 0), textcoords="offset points",
                va="center", fontsize=9, color=color)

zero_line(ax, vertical=False)
ax.set_title("Effect of a 600 kcal meal by how much of one group it contains")
ax.set_xlabel("grams in the meal (each group in its own basis)")
ax.set_ylabel("Δ years of life")
ax.set_xlim(0, 470)
ax.tick_params(length=0)
fig.tight_layout()
```

Every curve starts *below* zero at zero grams. A 600 kcal meal containing none
of a protective group still displaces a quarter of the baseline diet, and that
displaced share contained some. The intercept is the cost of the displacement;
the slope is what the meal gives back.

## Diminishing returns and the plateau

Whole grains rise steeply at first and then flatten. Two mechanisms produce
that, and it is worth separating them.

```{code-cell} ipython3
fine = np.arange(0, 301, 5)
wg = [mh.assess_meal({"whole_grains": float(g)}, 600, "USA", mode="median")
      .delta_yll_local_total for g in fine]
marginal = np.gradient(wg, fine)

fig, (ax_level, ax_marg) = plt.subplots(2, 1, figsize=(7.2, 5.0), sharex=True,
                                        height_ratios=[3, 2])

ax_level.plot(fine, wg, color=GAIN)
zero_line(ax_level, vertical=False)
ax_level.set_ylabel("Δ years of life")
ax_level.set_title("Whole grains, 600 kcal meal, USA median adult")
ax_level.tick_params(length=0)

ax_marg.plot(fine, marginal * 100, color=SERIES[3])
ax_marg.set_ylabel("years per 100 g")
ax_marg.set_xlabel("whole grains in the meal (g, dry weight)")
ax_marg.set_title("Marginal value of the next 100 g")
ax_marg.tick_params(length=0)
ax_marg.set_ylim(bottom=0)

fig.tight_layout()
```

The first 100 g buys far more than the fourth does. Part of that is the
log-linear shape of the relative-risk curve, which has diminishing returns
throughout. The rest is the {term}`TMREL`: each bundled curve is clipped at the
intake beyond which GBD judges there is no further benefit, so past that point
extra grams change nothing at all. The flat tail is the model saying "enough",
not the model running out of data.

## Where the baseline sits

The country's own intake marks the point on each curve where the meal is
neither better nor worse than what it replaces.

```{code-cell} ipython3
baseline = mh.assess_meal({}, 0.0, "USA").baseline_exposure
for group in curves:
    print(f"{group:<16} US baseline {baseline[group]:6.1f} g/day")
```

This is why a meal must be judged against a country, never in the abstract. In
a country eating 4 g of red meat a day, 150 g in a meal is an enormous
increase; in one eating 73 g, it is a moderate one, and the curve is flatter
there.

## Next

[Age](age_gradient.md) varies who is eating rather than what.
