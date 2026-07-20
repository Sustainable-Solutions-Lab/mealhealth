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

# The same meal across countries

Hold the meal fixed and vary the country, and the answer moves by nearly a
factor of ten. That is not noise: the model compares a meal against the local
baseline diet and weights the result by the local disease burden, so the country
is half the question.

```{code-cell} ipython3
:tags: [remove-output]

from mhstyle import GAIN, LOSS, apply_style, sign_colors, zero_line
import matplotlib.pyplot as plt

import mealhealth as mh

apply_style()
```

All 175 countries take about five seconds.

```{code-cell} ipython3
burger = {"red_meat": 150, "processed_meat": 30}

results = {
    country: mh.assess_meal(burger, 900, country, mode="median",
                            sodium_mg=1500)
    for country in mh.list_countries()
}
values = {c: r.delta_yll_local_total for c, r in results.items()}

print(f"{len(values)} countries")
print(f"range {min(values.values()):+.2f} to {max(values.values()):+.2f} years")
```

## The distribution

```{code-cell} ipython3
fig, ax = plt.subplots(figsize=(7.2, 3.2))
ax.hist(list(values.values()), bins=32, color=LOSS, edgecolor="#fcfcfb",
        linewidth=0.8)
zero_line(ax)
ax.set_title("Effect of the same burger, eaten daily, in 175 countries")
ax.set_xlabel("Δ years of life, median adult, local life table")
ax.set_ylabel("countries")
ax.tick_params(length=0)
ax.grid(axis="x", visible=False)
fig.tight_layout()
```

Every country is negative — a daily burger is bad news everywhere — but the harm
runs from 0.44 years in French Guiana to 4.11 in Vanuatu. The bulk of the
distribution sits between one and two and a half years, with a long tail of
countries where the same meal does far more damage.

## The extremes

```{code-cell} ipython3
ranked = sorted(values.items(), key=lambda kv: kv[1])
selection = ranked[:8] + ranked[-8:]

fig, ax = plt.subplots(figsize=(7.2, 5.0))
names = [c for c, _ in selection]
vals = [v for _, v in selection]
ax.barh(names, vals, color=sign_colors(vals), height=0.66)
zero_line(ax)
ax.set_title("Largest and smallest effect, by country")
ax.set_xlabel("Δ years of life")
ax.tick_params(length=0)
ax.grid(axis="y", visible=False)
ax.invert_yaxis()
fig.tight_layout()
```

## Why the spread

Three inputs differ by country, and they pull in different directions.

```{code-cell} ipython3
for country in ["IND", "USA", "FRA", "JPN"]:
    r = results[country]
    baseline = r.baseline_exposure
    print(f"{country}  ΔYLL {r.delta_yll_local_total:+.2f}   "
          f"baseline {r.baseline_kcal:.0f} kcal   f={r.f:.2f}   "
          f"red meat {baseline['red_meat']:5.1f} g/day   "
          f"processed {baseline['processed_meat']:4.1f} g/day")
```

A lower baseline calorie intake means the same 900 kcal meal displaces a larger
share of the day, so `f` falls and the meal dominates more of the diet. A lower
baseline red-meat intake means the meal's 150 g is a larger *increase* over
what was already being eaten, and the risk curves are steepest at low intake.
India has both — a 2195 kcal baseline and just 4.3 g/day of red meat against
America's 73.3 — which is why the same burger costs more than twice as many
years there.

The disease burden matters too, in the opposite direction: a country where
fewer people die of heart disease has fewer years available to save or lose.

## A caution

This is exactly the comparison where the choice of life table changes the
picture. `delta_yll_local_total` weights each death by local remaining life
expectancy, so a country with lower life expectancy shows a smaller effect
partly *because* people there die younger of other causes.

```{code-cell} ipython3
fig, ax = plt.subplots(figsize=(6.4, 4.4))
local = [values[c] for c in values]
standard = [results[c].delta_yll_standard_total for c in values]

ax.scatter(local, standard, s=18, color=GAIN, alpha=0.55, edgecolor="none")
lims = [min(local + standard) * 1.05, 0.1]
ax.plot(lims, lims, color="#a9a8a2", linewidth=1.0, linestyle=(0, (4, 3)),
        label="equal")
ax.set_xlabel("Δ years, local life table")
ax.set_ylabel("Δ years, GBD standard life table")
ax.set_title("Local and standard anchors disagree by country")
ax.tick_params(length=0)
ax.legend(loc="upper left")
fig.tight_layout()
```

Every point sits below the diagonal — the standard anchor always reports a
larger magnitude — but not by a constant factor. For cross-country comparison,
the standard anchor is the defensible choice, because it applies the same
longevity standard everywhere. Say which one you used.

## Next

[Dose and response](dose_response.md) fixes the country and varies the amount
instead.
