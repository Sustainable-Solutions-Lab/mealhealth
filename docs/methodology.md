<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Methodology

## Overview

For a meal described in food-group terms, `mealhealth` answers: *if an average
person in country `c` ate this meal every day instead of their current diet (at
the same total calories), how would their diet-attributable years of life lost
(YLL) change?* Positive ΔYLL means years **gained** (burden reduced); negative
means years **lost**.

All quantities are **relative to the country's baseline diet**, so no
theoretical-minimum-risk (TMREL) reference is needed.

## 1. The substituted diet

The user supplies the meal's total energy `C_meal` (kcal) and the mass of each
risk-factor food group it contains. The baseline diet is scaled down to keep
total calories constant and the meal is added on top:

```
f   = (C_base − C_meal) / C_base          (clamped to [0, 1])
x_r = f · baseline_r + meal_r             (per risk-factor group r)
```

`C_base` is the country's baseline daily energy intake. If `C_meal ≥ C_base`
then `f = 0` (the meal becomes the whole day's diet) and a warning is emitted.

Foods outside the risk groups (poultry, fish, eggs, oils, refined grains, …)
are **not** entered as food groups; they influence the result only through
`C_meal`, i.e. via caloric displacement of the baseline.

## 2. Relative risk and PAF

For each (risk factor `r`, disease cause `d`) pair, the relative risk
`RR_{r,d}(x_r)` is read off the GBD dose–response curve by **log-linear
interpolation** (linear interpolation of `log RR` between the empirical
exposure knots, clamped flat beyond the data range). Risk factors combine
multiplicatively per cause:

```
RR_d(x) = Π_r  RR_{r,d}(x_r)            (product over r affecting cause d)
```

The change relative to baseline is captured by the population attributable
fraction:

```
PAF_d(x) = 1 − RR_d(x) / RR_d(x_base)
```

`PAF_d > 0` ⇒ the meal lowers cause-`d` risk versus baseline; `< 0` ⇒ it raises
it.

## 3. From PAF to ΔYLL — the YLL anchor `Y_d`

```
ΔYLL_d(x) = PAF_d(x) · Y_d           Total ΔYLL = Σ_d ΔYLL_d
```

The anchor `Y_d` and the RR curve used differ by **age mode**.

### (a) Population mode

A population-level **annual** quantity (matches `food-opt`). The relative risk
uses the **YLL-weighted effective curve** across adult age groups:

```
log RR^eff_{r,d}(x) = Σ_a w_{a,d} · log RR_{r,d,a}(x)
w_{a,d}             = YLL_{c,d,a} / Σ_a YLL_{c,d,a}
```

where `YLL_{c,d,a} = m_{c,d,a} · P_{c,a} · e_a` is reconstructed from the
cause/age death rate `m`, the age-band population `P`, and the remaining life
expectancy `e_a` from the country life table. The anchor is the **total
observed YLL for cause `d`** in the country, `Y_d = Σ_a YLL_{c,d,a}`. This is
the burden generated under the baseline diet, so scaling it by the relative
change `PAF_d` gives the new burden.

### (b) Median person / (c) person of given age `a0`

**Individual lifetime** quantities. These do *not* reuse the population annual
anchor. Using the age-specific RR curve at each future age, the expected change
in remaining-lifetime YLL from cause `d` for someone currently aged `a0` is:

```
ΔYLL_d = Σ_{a ≥ a0}  S(a | a0) · (m_{c,d,a} · n_a) · e_a · PAF_{d,a}(x)
```

* `S(a | a0) = l_a / l_{a0}` — probability of surviving from `a0` to age band
  `a`, from the life-table survivorship column `l_x`.
* `m_{c,d,a} · n_a` — expected cause-`d` deaths in band `a` per person entering
  it (annual death rate × band width `n_a`; the open 95+ interval uses its
  remaining life expectancy as the effective width).
* `e_a` — remaining life expectancy at age `a` (years lost per such death).
* `PAF_{d,a}(x) = 1 − RR_{d,a}(x)/RR_{d,a}(x_base)`, evaluated **age by age**
  with the age-specific RR curve, because the dietary effect attenuates with
  age for cardiovascular causes.

Mode (b) sets `a0` to the population-weighted median adult age; mode (c) uses
the supplied age. This is equivalent to the expected change in age at death
from cause `d`. (The individual formula is validated against an explicit
hand-calculation in `tests/test_individual_handcalc.py`.)

## 4. Single-meal attribution

The headline figure is "years lost/gained if you ate this meal *for the rest of
your life*". A single-meal number (`per_meal_marginal`) is the lifetime effect
divided evenly over the meals in a lifetime — a **linear/marginal attribution,
not a biological single-meal effect** — and is only defined for the individual
lifetime modes.

## 5. Cause/risk-factor map

Same as `food-opt`, with processed meat added from its own GBD curves:

| Risk factor      | CHD | Stroke | T2DM | CRC |
|------------------|:---:|:------:|:----:|:---:|
| fruits           |  ✓  |   ✓    |  ✓   |     |
| vegetables       |  ✓  |   ✓    |      |     |
| whole grains     |  ✓  |   ✓    |  ✓   |  ✓  |
| legumes          |  ✓  |        |      |     |
| nuts & seeds     |  ✓  |        |  ✓   |     |
| red meat         |  ✓  |   ✓    |  ✓   |  ✓  |
| processed meat   |  ✓  |        |  ✓   |  ✓  |

"Stroke" is restricted to **ischemic** stroke (the atherosclerotic pathway diet
acts on); the mortality data is filtered to ischemic stroke to match.

## 6. Relative-only fallback

Where the absolute-YLL burden data cannot be used, `relative_only=True` reports
just the per-cause `PAF_d` (the % change in diet-attributable risk). This needs
only the RR curves and the baseline exposure, not mortality or life tables.

## Caveats

* "Years lost/gained if you ate this for the rest of your life" is the headline;
  any single-meal number is a marginal attribution, not a biological
  single-meal effect.
* Foods outside the GBD risk groups affect the result only via caloric
  displacement of the baseline.
* The population-mode YLL anchor is reconstructed as
  `deaths × remaining life expectancy` using the country's own (period) life
  table, rather than GBD's aspirational standard life table; the headline
  metric is therefore "expected years of life lost at local life expectancy".
* Additional dietary risk factors (sodium, sugar-sweetened beverages) are
  **not** modelled. GBD's sodium effect runs through a blood-pressure-mediated
  pathway in different units, and the SSB/sugar evidence is weak; both were
  optional "bonus" factors in the spec and are out of scope here. The
  architecture (a `risk_factor` with its own RR curve and baseline exposure)
  would accommodate them if suitable dose-response data were added.
* Red-meat RR uses the literature log-linear curves carried over from
  `food-opt` (Bechthold et al. 2019 for CHD/Stroke, Li et al. 2024 for T2DM,
  Chan et al. 2011 for CRC), which are calibrated on *unprocessed* red meat and
  thus appropriate now that processed meat is separated out. Processed meat uses
  the GBD 2019 dose–response curves directly.
