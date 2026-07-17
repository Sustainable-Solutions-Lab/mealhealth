<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Methodology

## Overview

For a meal described in food-group terms, `mealhealth` answers: *if an average
person in country $c$ ate this meal every day instead of their current diet (at
the same total calories), how would their diet-attributable years of life lost
(YLL) change?* Positive $\Delta\mathrm{YLL}$ means years **gained** (burden
reduced); negative means years **lost**.

All quantities are **relative to the country's baseline diet**, so the PAF below
does not compare the meal directly with a TMREL. Dietary curves are clipped at
their GBD 2023 TMREL during preparation. Sodium is the exception: its uncertain
urinary-sodium TMREL is integrated explicitly in the mediator calculation. See
[Data sources](data_sources.md).

```{figure} _static/method_overview.svg
:alt: A meal is substituted into the country baseline diet at equal calories; the resulting change in each food group's intake is read off its risk curve and turned into a change in years of life.
:width: 100%

The three steps in outline. The meal displaces part of the day's baseline diet
at equal calories (step 1); the resulting change in intake moves each food group
along its own risk curve, giving the change in risk relative to baseline
(step 2); that change, weighted by the local disease burden, becomes the net
effect on years of life (step 3). In the third panel each bar is a disease's
burden and the hatched tail is how far this meal shifts it. Proportions are
illustrative; the terms below make each step precise.
```

## 1. The substituted diet

You supply the meal's total energy $C_{\mathrm{meal}}$ (kcal), the mass of each
risk-factor food group it contains, and any optional nutrient-factor amount.
The baseline diet is scaled down to hold total calories constant, and the meal
is added on top:

$$
\begin{aligned}
f &= \operatorname{clip}\!\left(
    \frac{C_{\mathrm{base}} - C_{\mathrm{meal}}}{C_{\mathrm{base}}},
    0, 1
\right), \\
x_r &= f x_{r,\mathrm{base}} + x_{r,\mathrm{meal}} .
\end{aligned}
$$

$C_{\mathrm{base}}$ is the country's baseline daily energy intake. If
$C_{\mathrm{meal}} \ge C_{\mathrm{base}}$, then $f=0$ (the meal becomes the
whole day's diet) and a warning is emitted.

Foods outside the risk groups (poultry, fish, eggs, oils, refined grains, …)
are **not** entered as food groups; they influence the result only through
$C_{\mathrm{meal}}$, i.e. via caloric displacement of the baseline.

### Nutrient factors

Seafood omega-3 is supplied as EPA + DHA in mg per meal and converted to g/day
at the API boundary. Sodium is supplied as elemental sodium in mg per meal and
converted through the mediator described below. Unlike a missing food-group
key, which means zero grams, an omitted nutrient (`None`) is not assessed. An
explicit `0.0` is a measured zero: the meal adds none but still displaces the
country baseline.

### Sodium mean-shift approximation

For country $c$, adult age $a$, and sex $s$, let $u_0$ be GBD mean 24-hour
urinary sodium and $b_0$ mean systolic blood pressure. With meal sodium $m$ in
dietary g/day and baseline scale $f$, the substituted urinary mean is

$$
u_1 = f u_0 + 0.928m .
$$

The recovery fraction 0.928 and central chronic response of 2.42 mm Hg per
g/day urinary sodium are taken from the reviewed sodium-to-SBP references. GBD
specifies a sodium TMREL uniformly distributed from 1 to 5 g/day. The model
does not replace that interval with its 3 g/day midpoint: it deterministically
integrates the risk ratio over $t \sim \operatorname{Uniform}(1,5)$, using
$u_{\mathrm{eff}}=\max(u,t)$.

For each TMREL value, the mediated SBP change is

$$
\begin{aligned}
\Delta b(t) &= 2.42\left[\max(u_1,t)-\max(u_0,t)\right], \\
q_d(t) &=
\frac{\mathrm{RR}_{\mathrm{SBP},d,a}\!\left(b_0+\Delta b(t)\right)}
     {\mathrm{RR}_{\mathrm{SBP},d,a}(b_0)} .
\end{aligned}
$$

and stomach cancer uses its direct urinary-sodium curve in the analogous
ratio. The stratum sodium ratio is the uniform-TMREL mean of $q_d(t)$. This is
a deliberately simple **mean-field approximation**: evaluating a nonlinear RR
curve at mean SBP is generally not the same as averaging risk over individual
SBP. The result has no sodium uncertainty interval and must not be interpreted
as an individualized prediction. A future implementation can replace this
step with within-stratum sodium/SBP distributions and coherent uncertainty
draws without changing the public nutrient input.

## 2. Relative risk and PAF

For each risk factor $r$ and disease cause $d$, the relative risk
$\mathrm{RR}_{r,d}(x_r)$ is read off the GBD 2023 Burden-of-Proof
dose–response curve by
**log-linear interpolation** (linear interpolation of $\log\mathrm{RR}$ between the
exposure knots, clamped flat beyond the data range). The Burden-of-Proof tool
provides one age-aggregated curve per pair; the bundled curves restore the
per-age structure with a curated multiplicative log-RR attenuation (GBD's 60-64
reference age) and are clipped at the GBD 2023 TMREL. Risk factors combine
multiplicatively per cause:

$$
\mathrm{RR}_d(\mathbf{x})
= \prod_{r\,:\,r\rightarrow d} \mathrm{RR}_{r,d}(x_r) .
$$

The change relative to baseline is captured by the population attributable
fraction:

$$
\mathrm{PAF}_d(\mathbf{x})
= 1 - \frac{\mathrm{RR}_d(\mathbf{x})}
           {\mathrm{RR}_d(\mathbf{x}_{\mathrm{base}})} .
$$

$\mathrm{PAF}_d>0$ means the meal lowers cause-$d$ risk versus baseline;
$\mathrm{PAF}_d<0$ means it raises it.

## 3. From PAF to ΔYLL — local and standard anchors

$$
\begin{aligned}
\Delta\mathrm{YLL}_d(\mathbf{x})
  &= \sum_{a,s}\mathrm{YLL}_{c,d,a,s}
     \mathrm{PAF}_{d,a,s}(\mathbf{x}), \\
\Delta\mathrm{YLL}_{\mathrm{total}}
  &= \sum_d \Delta\mathrm{YLL}_d .
\end{aligned}
$$

Every assessment reports two versions:

* `delta_yll_local_total` uses remaining life expectancy from the country's UN
  WPP period life table. It estimates years gained or lost under current local
  mortality conditions. `delta_yll_total` is an alias for this value.
* `delta_yll_standard_total` uses the common GBD 2023 theoretical minimum-risk
  reference life table. It measures potential years gained or lost relative to
  GBD's aspirational longevity standard and is the appropriate output for
  comparison with published GBD YLL estimates.

The burden anchor and RR curve used differ by **age mode** and life-table choice.

### (a) Population mode

A population-level **annual** quantity evaluated on exact country × age × sex
burden strata:

$$
\begin{aligned}
\mathrm{YLL}_{c,d,a,s}
  &= m_{c,d,a,s} P_{c,a,s} e_{c,a,s}, \\
\mathrm{PAF}_{d,a,s}(\mathbf{x})
  &= 1 - \frac{\mathrm{RR}_{d,a,s}(\mathbf{x})}
              {\mathrm{RR}_{d,a,s}(\mathbf{x}_{\mathrm{base}})} .
\end{aligned}
$$

The calculation is performed once with sex-specific local life expectancy and
once with the common GBD reference life expectancy. Each reported PAF divides
the summed change by the corresponding total observed cause YLL across all ages
and both sexes. Food-group curves are currently sex-invariant, but retaining
sex in burden aggregation is necessary for sodium and avoids a country-wide
effective-RR approximation.

### (b) Median person / (c) person of given age $a_0$

**Individual lifetime** quantities. These do *not* reuse the population annual
anchor. Using the age-specific RR curve at each future age, the expected change
in remaining-lifetime YLL from cause $d$ for someone currently aged $a_0$ is:

$$
\Delta\mathrm{YLL}_d
= \sum_s \pi_{c,s,a_0}
  \sum_{a\ge a_0}
  S_{c,s}(a\mid a_0)
  \left(m_{c,d,a,s}n_a\right)
  e_{c,a,s}
  \mathrm{PAF}_{d,a,s}(\mathbf{x}) .
$$

* $\pi_{c,s,a_0}$ is the male/female population share at the starting age.
* $S_{c,s}(a\mid a_0)=l_{a,s}/l_{a_0,s}$ is sex-specific local survival.
* $m_{c,d,a,s}n_a$ is expected cause-$d$ deaths in band $a$ per person entering
  it (annual death rate times band width $n_a$; the open 95+ interval uses its
  remaining life expectancy as the effective width).
* $e_{c,a,s}$ is either local or GBD-standard remaining life expectancy at age
  $a$ (years lost per such death). Local survivorship $S(a\mid a_0)$ and time
  at risk remain country-specific in both versions.
* $\mathrm{PAF}_{d,a,s}(\mathbf{x})$ is evaluated **age by age** with the
  age-specific RR curve, because the dietary effect attenuates with age for
  cardiovascular causes.

Mode (b) sets $a_0$ to the combined-sex population-weighted median adult age;
mode (c) uses the supplied age. Both are population-average results conditional
on being alive at $a_0$, not results for a person of a specified sex. The formula
is validated against an explicit hand calculation in
`tests/test_individual_handcalc.py`.

## 4. Single-meal attribution

The headline figure is "years lost/gained if you ate this meal *for the rest of
your life*". A single-meal number (`per_meal_marginal`) is the lifetime effect
divided evenly over the meals in a lifetime — a **linear/marginal attribution,
not a biological single-meal effect** — and is only defined for the individual
lifetime modes.

## 5. Cause/risk-factor map

Each risk factor acts on the GBD-mapped causes below; processed meat is added
from its own GBD curves:

| Risk factor      | CHD | Stroke | T2DM | CRC |
|------------------|:---:|:------:|:----:|:---:|
| fruits           |  ✓  |   ✓    |  ✓   |     |
| vegetables       |  ✓  |   ✓    |      |     |
| whole grains     |  ✓  |   ✓    |  ✓   |  ✓  |
| legumes          |  ✓  |        |      |     |
| nuts & seeds     |  ✓  |        |      |     |
| red meat         |  ✓  |   ✓    |  ✓   |  ✓  |
| processed meat   |  ✓  |        |  ✓   |  ✓  |
| seafood omega-3  |  ✓  |        |      |     |

Sodium has a separate mediated outcome map:

| Path | Burden causes |
|------|---------------|
| direct urinary sodium | stomach cancer |
| SBP → ischemic heart disease | CHD |
| SBP → combined stroke curve | ischemic stroke and haemorrhagic stroke |
| SBP → CKD | chronic kidney disease |

"Stroke" is restricted to **ischemic** stroke (the atherosclerotic pathway diet
acts on); the mortality data is filtered to ischemic stroke to match.
WHO GHE publishes intracerebral and subarachnoid haemorrhage together, and its
two chronic-kidney categories are summed. This aggregation is exact within the
model because the component causes use the same relative-risk curve. WHO does
not publish standalone aortic-aneurysm or peripheral-arterial-disease rates, so
those sodium pathways are excluded instead of applying a risk curve to WHO's
much broader residual circulatory category.

## 6. Relative-only fallback

`relative_only=True` reports just the per-cause PAFs and suppresses absolute
YLL. It deliberately uses the same sex-specific burden weights as the full
result, so it still requires bundled mortality, population, and life tables.

## Caveats

* "Years lost/gained if you ate this for the rest of your life" is the headline;
  any single-meal number is a marginal attribution, not a biological
  single-meal effect.
* Foods outside the GBD risk groups affect the result only via caloric
  displacement of the baseline.
* `delta_yll_local_total` is reconstructed as deaths times remaining life
  expectancy using the country's own period life table; `delta_yll_total`
  remains an alias. `delta_yll_standard_total` uses GBD's aspirational
  reference life table and is a standardized potential-life-loss measure, not
  a forecast of years that this intervention alone would realize under current
  local mortality.
* Sodium uses a central mean-shift approximation. It does not propagate
  uncertainty in baseline exposure, recovery, the sodium-to-SBP slope, or RR
  curves, and it does not represent within-stratum sodium or SBP variation.
  These omissions are expected to matter because the RR curves are nonlinear.
* Sugar-sweetened beverages are not modelled.
* Red-meat RR uses literature log-linear curves
  (Bechthold et al. 2019 for CHD/Stroke, Li et al. 2024 for T2DM,
  Chan et al. 2011 for CRC), which are calibrated on *unprocessed* red meat and
  thus appropriate now that processed meat is separated out. Processed meat uses
  the GBD 2023 Burden-of-Proof dose–response curves directly (CHD/T2DM/CRC; no
  ischemic stroke curve). `nuts_seeds` maps to CHD only because GBD 2023 does
  not provide a T2DM curve. Seafood omega-3 uses the GBD 2023 CHD curve
  directly and is clipped at its 0.565 g/day midpoint TMREL.
