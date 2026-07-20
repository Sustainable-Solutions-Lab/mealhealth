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

# Under the hood

The bundled tables are ordinary dataframes, and `mealhealth.data` loads them.
This page is for checking the model rather than using it — plotting the curves
and baselines that everything else rests on.

These loaders are cached and read-only. Treat them as a public surface for
inspection; the numbers they return are the same ones `assess_meal` uses.

```{code-cell} ipython3
:tags: [remove-output]

from mhstyle import GAIN, LOSS, SERIES, apply_style, zero_line
import matplotlib.pyplot as plt
import numpy as np

import mealhealth as mh
from mealhealth import data

apply_style()
```

## The relative-risk curves

```{code-cell} ipython3
rr = data.relative_risks()
rr.head()
```

One curve per risk factor, cause and age band. Here is red meat and coronary
heart disease at three ages, with the US baseline intake marked.

```{code-cell} ipython3
baseline = mh.assess_meal({}, 0.0, "USA").baseline_exposure

fig, ax = plt.subplots(figsize=(7.2, 4.0))
for age, color in zip(["30-34", "60-64", "85-89"], SERIES, strict=False):
    curve = rr[(rr["risk_factor"] == "red_meat") & (rr["cause"] == "CHD")
               & (rr["age"] == age)].sort_values("exposure_g_per_day")
    ax.plot(curve["exposure_g_per_day"], curve["rr_mean"], color=color,
            label=f"age {age}")

ax.axvline(baseline["red_meat"], color="#a9a8a2", linewidth=1.0,
           linestyle=(0, (4, 3)))
ax.annotate("US baseline", (baseline["red_meat"], 1.005), xytext=(6, 0),
            textcoords="offset points", fontsize=9, color="#52514e")
ax.axhline(1.0, color="#d8d7d2", linewidth=1.0)
ax.set_title("Red meat → coronary heart disease")
ax.set_xlabel("intake (g/day, fresh raw weight)")
ax.set_ylabel("relative risk")
ax.tick_params(length=0)
ax.legend()
fig.tight_layout()
```

The age bands are the attenuation at work: the same intake carries more relative
risk for a 30-year-old than an 85-year-old. The 60–64 band is the reference the
others are normalised against.

## Where the curves stop

Every dietary curve is clipped at its TMREL, which is why the protective ones
flatten.

```{code-cell} ipython3
fig, ax = plt.subplots(figsize=(7.6, 4.2))
protective = ["vegetables", "whole_grains", "legumes", "fruits", "nuts_seeds"]

for group, color in zip(protective, SERIES, strict=False):
    curve = rr[(rr["risk_factor"] == group) & (rr["cause"] == "CHD")
               & (rr["age"] == "60-64")].sort_values("exposure_g_per_day")
    if curve.empty:
        continue
    ax.plot(curve["exposure_g_per_day"], curve["rr_mean"], color=color)
    ax.annotate(group.replace("_", " "),
                (curve["exposure_g_per_day"].iloc[-1], curve["rr_mean"].iloc[-1]),
                xytext=(6, 0), textcoords="offset points", va="center",
                fontsize=9, color=color)

ax.axhline(1.0, color="#d8d7d2", linewidth=1.0)
ax.set_title("Protective groups → coronary heart disease, age 60–64")
ax.set_xlabel("intake (g/day, each in its own basis)")
ax.set_ylabel("relative risk")
ax.set_xlim(right=ax.get_xlim()[1] * 1.18)
ax.tick_params(length=0)
fig.tight_layout()
```

Each line ends where its curve is clipped. Past that point the model returns a
flat relative risk, which is what produces the plateau seen in
[Dose and response](dose_response.md).

## Baseline diets

```{code-cell} ipython3
exposure = data.baseline_exposure()
pivot = exposure.pivot(index="country", columns="risk_factor",
                       values="exposure_g_per_day")

fig, ax = plt.subplots(figsize=(7.6, 4.0))
groups = ["fruits", "vegetables", "whole_grains", "legumes", "nuts_seeds",
          "red_meat", "processed_meat"]
ax.boxplot([pivot[g].dropna() for g in groups],
           tick_labels=[g.replace("_", " ") for g in groups],
           medianprops=dict(color=GAIN, linewidth=2),
           boxprops=dict(color="#a9a8a2"),
           whiskerprops=dict(color="#a9a8a2"),
           capprops=dict(color="#a9a8a2"),
           flierprops=dict(marker="o", markersize=3, markerfacecolor=LOSS,
                           markeredgecolor="none", alpha=0.5))
ax.set_title("Adult baseline intake across 175 countries")
ax.set_ylabel("g/day")
ax.tick_params(length=0, axis="x", labelrotation=20)
ax.grid(axis="x", visible=False)
fig.tight_layout()
```

The spread here is what drives the cross-country variation in
[The same meal across countries](across_countries.md). Red meat in particular
ranges over more than an order of magnitude.

## Burden, life tables, everything else

```{code-cell} ipython3
for name, frame in [
    ("relative_risks", data.relative_risks()),
    ("baseline_exposure", data.baseline_exposure()),
    ("baseline_calories", data.baseline_calories()),
    ("baseline_mediators", data.baseline_mediators()),
    ("mortality", data.mortality()),
    ("population", data.population()),
    ("local_life_table", data.local_life_table()),
    ("standard_life_table", data.standard_life_table()),
    ("sodium_relative_risks", data.sodium_relative_risks()),
]:
    print(f"{name:<24}{len(frame):>8,} rows   {list(frame.columns)}")
```

Column schemas are documented in `src/mealhealth/data/DATA_PROVENANCE.md`, and
where each table comes from in [Data sources](../model/data_sources.md). If you
want to regenerate them from the upstream releases rather than trusting the
checked-in copies, see
[Rebuilding the bundled data](../development/data_build.md).
