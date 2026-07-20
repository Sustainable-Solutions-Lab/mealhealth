<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Limitations

Read this before publishing a number. The model is deliberately simple in
places, and several of the simplifications bias results in directions worth
knowing about. [Methodology](methodology.md) gives the formulas these caveats
attach to; [Data sources](data_sources.md) documents the inputs.

## What the headline number is

"Years lost or gained if you ate this meal for the rest of your life" is the
estimand. It is not the effect of eating the meal once. `per_meal_marginal()`
divides the lifetime effect evenly over a nominal lifetime's meals, which is a
linear attribution convention, not a biological single-meal effect — nothing in
the model resolves what one meal does to a body.

Population mode reports an **annual** population total under a
counterfactual where everyone in the country eats the meal daily. The
individual modes report a **lifetime** per-person quantity. The two are
different measures in different units and must not be compared or added.

`delta_yll_standard_total` uses GBD's aspirational reference life table. It
measures potential years of life lost against a longevity standard, which is
what makes it comparable with published GBD estimates. It is not a forecast of
years this change alone would realise under current local mortality; that
reading belongs to `delta_yll_local_total`, and even there only as an
approximation.

## Exposure is a mean, and the curves are not linear

The model evaluates each relative-risk curve at a country-level (or
country-age-sex) **mean** exposure. Real populations have distributions, and
because the curves are nonlinear, the risk at the mean intake is generally not
the mean risk across people. GBD's own attributable-burden estimates integrate
over exposure distributions; mealhealth does not, because the bundled exposure
files supply means and uncertainty in the mean, not quantiles across
individuals.

Nothing propagates uncertainty. Relative-risk curve bounds, exposure bounds,
and the sodium response coefficients all have published intervals; the model
carries central values only and reports no interval. Treat the outputs as point
estimates from a specific set of choices rather than as a distribution over
plausible values.

## Sodium is a mean-shift approximation

Sodium enters through a deterministic country-age-sex shift in mean systolic
blood pressure, using a single central response coefficient of 2.42 mm Hg per
g/day of urinary sodium. The uncertain 1–5 g/day TMREL is integrated
explicitly rather than collapsed to its midpoint, but everything else is a
point estimate.

This means sodium results ignore within-stratum variation in both sodium intake
and blood pressure, carry no uncertainty interval, and cannot be read as a
prediction for an individual. They take no account of personal blood pressure,
antihypertensive treatment, kidney function, or salt sensitivity. Because the
SBP curves are nonlinear, evaluating them at a stratum mean is expected to
misstate the stratum's true mean risk; the direction depends on curvature over
the relevant range. A distributional treatment is designed but not implemented
— see the [sodium design note](../development/design/sodium.md).

## Coverage gaps

Sugar-sweetened beverages, trans fatty acids, polyunsaturated fatty acids,
fibre, calcium and milk are GBD dietary risk factors that mealhealth does not
model. Alcohol is a GBD risk factor in its own right and is likewise absent. A
meal's effect through any of those pathways is simply missing, not estimated as
zero-with-uncertainty.

Foods outside the seven risk groups — poultry, fish (except through its EPA+DHA
content), eggs, oils, refined grains, potatoes, sugar, dairy — affect the result
only by displacing baseline diet in caloric terms. A 600 kcal meal of white rice
and chicken is modelled as 600 kcal of *not* eating the baseline diet, nothing
more.

`nuts_seeds` maps to coronary heart disease alone, because GBD 2023 publishes no
type-2 diabetes curve for it. Processed meat has no ischemic-stroke curve.
Sodium's aortic-aneurysm and peripheral-arterial-disease pathways are dropped
because WHO publishes no standalone mortality rates for them, and applying a
risk curve to WHO's much broader residual circulatory category would be worse
than omitting them.

## Burden data compromises

WHO GHE does not separate type 2 from all diabetes in its mortality series, so
the T2DM relative-risk curve is weighted by **broad diabetes** mortality. This
overstates the burden the curve acts on, by roughly the type-1 share.

WHO publishes one open `85+` band. Its rate is repeated across the model's
`85–89`, `90–94` and `95+` strata, which preserves the aggregate death count but
leaves the split of deaths and years lost within the open band approximate.

Five territories use documented proxies for mortality because WHO has no
separate Member State row: American Samoa uses Samoa, French Guiana uses France,
Puerto Rico uses the USA, Palestine uses Jordan, and Taiwan uses South Korea.
French Guiana additionally uses France as its GBD exposure proxy. Calorie
proxies are recorded per country in the source manifest. None of these should be
read as country-specific survey estimates.

## Relative risks are borrowed across ages and studies

The Burden-of-Proof tool publishes one age-aggregated curve per risk–cause pair.
The per-age structure is restored with a curated multiplicative log-RR
attenuation derived from the **GBD 2019** relative-risk workbook and normalised
at the 60–64 reference age. Mixing a 2023 curve level with a 2019 age shape is a
pragmatic choice, and any change in the age gradient between those rounds is
unmodelled.

Red-meat curves are literature log-linear fits (Bechthold et al. 2019 for
CHD and stroke, Li et al. 2024 for type 2 diabetes, Chan et al. 2011 for
colorectal cancer) rather than GBD's own, because they are calibrated on
unprocessed red meat — the right basis once processed meat is separated out. The
Burden-of-Proof red-meat curve supplies only the exposure grid.

Food-group curves are sex-invariant. Sex is nonetheless retained throughout
burden aggregation, because sodium's blood-pressure pathway is not
sex-invariant and because a country-wide effective-RR shortcut would introduce
its own error.

## Reference years do not all coincide

Mortality and population are 2020, life tables are the nearest available UN WPP
abridged year (2024), exposure is 2020, and intake is circa 2018–2020. The model
treats these as one contemporaneous snapshot.
