<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Interpreting results

`assess_meal` returns several numbers that look similar and mean quite
different things. This page says what each one is, and which comparisons
between them are legitimate.

## The sign

Positive means **years gained**, negative means **years lost**. This is the
opposite of the usual convention for a burden measure, and it is deliberate:
the quantity is a change in years of life lost, so a reduction in burden is a
positive change in life.

## The three modes are three different quantities

Take a burger — 150 g red meat, 60 g processed meat, 650 kcal — in the USA:

```python
mh.assess_meal(burger, 650, "USA").delta_yll_local_total                 # -3_112_021
mh.assess_meal(burger, 650, "USA", mode="median").delta_yll_local_total  #      -0.872
```

Both describe the same meal. Neither is more correct than the other, and the
factor of three million between them is not a discrepancy.

**Population mode** (the default) answers: if everyone in the country ate this
meal daily instead of their current diet, how would the country's *annual*
diet-attributable years of life lost change? Its units are years per year,
across a whole population, which is why the figures run to millions. Use it for
population-scale questions — policy scenarios, national dietary shifts, the
aggregate cost of a food.

**Median and age modes** answer: for one person, currently the median adult age
or a given age, how would their expected *remaining-lifetime* years of life lost
change if they ate this meal daily for the rest of their life? Units are years
per person. Use it for anything about an individual.

Never compare the two, never add them, and never divide one by the other to get
a per-capita figure — the population number is annual and the individual number
is lifetime, so the ratio has no interpretation.

Within the individual modes, the effect attenuates with age, because the risk
curves flatten and there is less remaining life to lose:

| Age | ΔYLL (years) |
|-----|--------------|
| 25  | −0.95 |
| 45  | −0.91 |
| 65  | −0.69 |
| 80  | −0.52 |

Both individual modes are population averages conditional on being alive at the
starting age, weighted over the sex composition at that age. They are not
results for a person of a specified sex, and not a prediction about any
particular person.

## Local and standard are two different anchors

Every assessment reports both, and for the meals above they differ by nearly
half:

```python
r = mh.assess_meal(burger, 650, "USA", mode="median")
r.delta_yll_local_total     # -0.872, the country's own life table
r.delta_yll_standard_total  # -1.295, GBD's reference life table
```

`delta_yll_local_total` (aliased as `delta_yll_total`) weights each averted or
added death by remaining life expectancy from the **country's own** UN WPP
period life table. It answers "how many years, under current local mortality
conditions".

`delta_yll_standard_total` uses GBD's **theoretical minimum-risk** reference
life table — an aspirational longevity standard, identical across countries. It
answers "how many years of *potential* life", and it is the number to use when
comparing against published GBD estimates or across countries with very
different life expectancy. The standard figure is always the larger in
magnitude, because the reference table assigns more remaining life at every age
than any real country's does.

Pick one for a given piece of analysis and say which you used. Mixing them
within a comparison is the most common way to produce a difference that is
really an artefact of the anchor.

## PAF and ΔYLL answer different questions

`causes[...].paf_local` is a fraction, not a percentage: `+0.23` means the meal
removes 23% of the country's coronary-heart-disease burden relative to the
baseline diet. It is a *relative* change, so a cause with a small absolute
burden can show a large PAF.

`causes[...].delta_yll_local` is that fraction weighted by how much burden the
cause actually carries. This is why coronary heart disease usually dominates the
total even when another cause has a larger PAF — it simply kills more people.

`relative_only=True` reports the PAFs and suppresses the absolute YLL. It does
not make the result data-free: the PAFs are still burden-weighted across age and
sex strata, so mortality, population and life tables are all still required.

## Risk attribution has a trap in it

`risk_attribution_local` splits the total ΔYLL across the risk factors, and the
parts sum to the whole. What surprises people is that groups the meal does not
contain show up with **negative** contributions:

```python
r = mh.assess_meal({"vegetables": 250, "whole_grains": 100, "legumes": 80}, 550, "USA",
                   mode="median")
r.risk_attribution_local
# {'fruits': -0.053, 'vegetables': +0.077, 'whole_grains': +0.295,
#  'legumes': +0.146, 'nuts_seeds': -0.000, 'red_meat': +0.052,
#  'processed_meat': +0.043}
```

That meal contains no fruit, and fruit costs it 0.053 years. The reason is
substitution: the meal displaces 21% of the day's baseline diet, including the
baseline's fruit, and fruit is protective. Meanwhile red meat and processed meat
show *positive* contributions for the same reason — the meal displaces some of
the baseline's meat without adding any.

So every number here is relative to the baseline diet, including for groups you
never mentioned. A meal is not penalised for containing red meat in the
abstract; it is assessed on whether it has more or less than the share of the
baseline diet it replaces.

## The per-meal figure

`per_meal_marginal()` divides a lifetime result evenly over a nominal
lifetime's meals. For the burger that is about −1.3 × 10⁻⁵ years, or seven
minutes.

Seven minutes of life per burger is a memorable number and a defensible
accounting convention. It is not a biological claim: nothing in the model
resolves what one meal does to a body, and the arithmetic assumes the lifetime
effect divides linearly, which it does not. Use it to communicate scale, and say
what it is when you do. It raises `ValueError` in population mode, where it
would mean nothing at all.

## Read the warnings

`result.warnings` is a list, usually empty. Two entries matter:

A **meal energy ≥ baseline** warning means the meal's calories exceed the
country's entire daily intake, so the baseline scale `f` clamped to zero and the
meal became the whole day's diet. The result is still computed, but it is
answering a different question than you probably asked.

A **sodium approximation** warning appears whenever `sodium_mg` is supplied.
It is not a problem with your input; it records that sodium goes through a
central stratum-mean approximation with no uncertainty interval. See
[Limitations](../model/limitations.md#sodium-is-a-mean-shift-approximation).

## Sanity checks worth doing

Check `result.f` and `result.baseline_kcal`. A 650 kcal meal against a US
baseline of 2597 kcal gives `f = 0.75`, meaning the meal replaces a quarter of
the day. If `f` is far from what you expect, `meal_kcal` is probably wrong, and
`meal_kcal` drives everything.

Compare across countries before trusting a single one. The same burger costs
0.71 years in France, 0.87 in the USA and 2.02 in India — the spread is real
and comes from different baseline diets, different disease burdens, and
different baseline calories, but a country that is a wild outlier is worth
investigating rather than reporting.

Assess an empty meal (`{}` with `meal_kcal=0`). Every output should be zero. If
it is not, something is wrong with the installation rather than with your meal.
