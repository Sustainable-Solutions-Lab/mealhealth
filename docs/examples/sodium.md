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

# Sodium

Sodium is the only factor that does not act on disease directly. It shifts mean
systolic blood pressure, and blood pressure carries the effect to three of its
four causes. That extra step brings extra caveats, and this page is as much
about them as about the numbers.

```{code-cell} ipython3
:tags: [remove-output]

from mhstyle import GAIN, LOSS, SERIES, apply_style, label_bars, sign_colors, zero_line
import matplotlib.pyplot as plt
import numpy as np

import mealhealth as mh

apply_style()
```

## Sodium is not salt

`sodium_mg` is **elemental sodium**, including what is in the ingredients, the
sauces, the cooking water and the salt cellar. Passing salt mass instead
overstates the exposure by about two and a half times.

```{code-cell} ipython3
salt_g = 3.0
print(f"{salt_g} g of salt = {salt_g * 1000 / 2.542:.0f} mg sodium")
```

For reference, a moderate restaurant main might carry 1000–1500 mg of sodium,
and WHO recommends staying under 2000 mg a day in total.

## Supplying it changes which diseases appear

Without `sodium_mg`, a result covers four causes. With it, three more appear —
they are reachable only through this pathway.

```{code-cell} ipython3
meal = {"vegetables": 180, "whole_grains": 70}

without = mh.assess_meal(meal, 650, "USA", mode="median")
with_sodium = mh.assess_meal(meal, 650, "USA", mode="median", sodium_mg=1200)

print("without sodium:", sorted(without.causes))
print("with sodium:   ", sorted(with_sodium.causes))
print(f"\nΔYLL without {without.delta_yll_local_total:+.3f}, "
      f"with {with_sodium.delta_yll_local_total:+.3f}")
print("\n" + with_sodium.warnings[0])
```

That warning appears on every sodium result. It is not about your input.

## The dose curve

```{code-cell} ipython3
sodium = np.arange(0, 3001, 100)
totals = [mh.assess_meal(meal, 650, "USA", mode="median", sodium_mg=float(s))
          .risk_attribution_local["sodium"] for s in sodium]

fig, ax = plt.subplots(figsize=(7.2, 3.8))
ax.plot(sodium, totals, color=LOSS)
zero_line(ax, vertical=False)
ax.set_title("Sodium's own contribution to the total")
ax.set_xlabel("sodium in the meal (mg)")
ax.set_ylabel("Δ years of life from sodium")
ax.tick_params(length=0)
fig.tight_layout()
```

At the left-hand end the contribution is *positive*: a meal with no sodium
displaces part of a baseline diet that has plenty, so it reduces exposure. The
curve crosses zero at the point where the meal's sodium matches the share of
baseline sodium it replaced, and turns harmful above that.

## Which causes carry it

```{code-cell} ipython3
salty = mh.assess_meal(meal, 650, "USA", mode="median", sodium_mg=2500)

def baseline_yll(cause):
    """Years from this cause without sodium — zero for causes sodium alone reaches."""
    result = without.causes.get(cause)
    return result.delta_yll_local if result else 0.0

contributions = {mh.CAUSE_LABELS[c]: r.delta_yll_local - baseline_yll(c)
                 for c, r in salty.causes.items()}
ordered = dict(sorted(contributions.items(), key=lambda kv: kv[1]))

fig, ax = plt.subplots(figsize=(7.2, 3.4))
values = list(ordered.values())
bars = ax.barh(list(ordered), values, color=sign_colors(values), height=0.62)
label_bars(ax, bars.patches, values, fmt="{:+.3f}")
zero_line(ax)
ax.set_title("Effect of adding 2500 mg of sodium, by cause")
ax.margins(x=0.3)
ax.tick_params(length=0)
ax.grid(axis="y", visible=False)
fig.tight_layout()
```

Coronary heart disease takes about two-thirds of the effect, through the
blood-pressure pathway. The two stroke categories and chronic kidney disease
share most of the rest.

Stomach cancer barely registers, which is worth noticing: it is the one cause
sodium reaches through a direct urinary-sodium curve rather than through blood
pressure, and at these intakes that curve is nearly flat. Colorectal cancer and
type 2 diabetes sit at exactly zero because sodium has no pathway to them at
all — they move only with the food groups.

## What this calculation is not

The pathway is a deterministic shift in the *mean* of each country × age × sex
stratum: mean urinary sodium moves, mean systolic blood pressure follows at
2.42 mm Hg per g/day, and risk is read off the curve at that new mean.

Three consequences follow, and none of them is visible in the number itself.

Evaluating a nonlinear curve at a mean is not the same as averaging risk over a
population whose blood pressure varies. The bundled exposure data gives means
and uncertainty in the mean, not the spread across people, so a distributional
treatment is not possible with what is shipped.

There is no uncertainty interval. The recovery fraction, the blood-pressure
slope and the risk curves all have published intervals; the model carries
central values only.

It says nothing about you. No personal blood pressure, no antihypertensive
treatment, no kidney function, no salt sensitivity.

The one uncertain quantity that *is* handled properly is the TMREL. GBD puts it
uniformly between 1 and 5 g/day, and the model integrates the risk ratio over
that interval rather than collapsing it to the 3 g/day midpoint.

[Limitations](../model/limitations.md#sodium-is-a-mean-shift-approximation)
states the same caveats for citation, and the
[sodium design note](../development/design/sodium.md) describes the
distributional model this one deliberately falls short of.

## Next

[Under the hood](under_the_hood.md) plots the curves this all rests on.
