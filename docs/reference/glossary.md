<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Glossary

```{glossary}
YLL
  Years of life lost. A death is counted as the remaining life expectancy the
  person would have had, so a death at 50 costs more years than a death at 85.
  mealhealth reports a *change* in YLL, written ΔYLL, and signs it so that
  **positive means years gained**.

ΔYLL
  The change in {term}`YLL` between the substituted diet and the country's
  baseline diet. Positive means the meal reduces burden.

PAF
  Population attributable fraction. Here defined relative to the baseline diet
  rather than to a theoretical minimum: `PAF = 1 − RR(x) / RR(x_base)`. A PAF
  of +0.23 means the meal removes 23% of that cause's burden compared with
  eating the baseline diet. It is a fraction, not a percentage.

RR
  Relative risk. How much more (or less) likely a disease is at one exposure
  level than another. mealhealth reads RR off a dose–response curve by
  log-linear interpolation and combines risk factors multiplicatively within a
  cause.

Dose–response curve
  The function mapping intake of a risk factor to relative risk for one
  disease. Bundled curves come from the GBD {term}`Burden of Proof` tool, are
  expanded across age bands with a curated attenuation table, and are clipped
  at the {term}`TMREL`.

TMREL
  Theoretical minimum-risk exposure level: the intake beyond which a curve
  plateaus and further consumption changes nothing. Because mealhealth measures
  everything relative to the baseline diet, the TMREL never enters the
  {term}`PAF` directly — it only shapes where each curve flattens. Sodium is
  the exception: its TMREL is genuinely uncertain (uniform on 1–5 g/day) and is
  integrated over rather than fixed.

Burden of Proof
  IHME's meta-analytic tool that publishes dose–response curves with
  evidence-strength ratings ("stars"). It serves one age-aggregated curve per
  risk–cause pair, which is why mealhealth restores the age structure
  separately.

Baseline diet
  The country's current average adult intake of each risk factor, from GBD 2023
  exposure estimates, with a calorie anchor from {term}`GDD-IA`. Every result is
  a comparison against this, which is why a meal can be penalised for a
  protective food it omits.

Substitution factor (`f`)
  How much of the baseline diet survives after the meal is added at constant
  calories: `f = (baseline_kcal − meal_kcal) / baseline_kcal`, clamped to
  [0, 1]. A 650 kcal meal against a 2600 kcal baseline gives `f = 0.75`.

Mass basis
  The convention in which a food group's mass is measured — fresh weight, dry
  uncooked weight, or as-eaten product weight. It differs by group, and
  supplying a mass in the wrong basis silently produces wrong numbers. See
  [Food groups](../guide/food_groups.md).

Risk factor
  A dietary exposure with its own curve. mealhealth models seven food groups
  plus two optional nutrient factors (seafood omega-3 and sodium).

Cause
  A modelled disease outcome: coronary heart disease, ischemic stroke, type 2
  diabetes, colorectal cancer, and — through sodium only — stomach cancer,
  haemorrhagic stroke and chronic kidney disease.

Mediator
  A risk factor that acts on disease through an intermediate physiological
  quantity rather than directly. Sodium is mediated through {term}`SBP` for
  three of its four causes.

SBP
  Systolic blood pressure. The pathway through which dietary sodium reaches
  heart disease, stroke and kidney disease in this model, using a central
  response of 2.42 mm Hg per g/day of urinary sodium.

Stratum
  One country × age band × sex cell. Burden is aggregated over strata, and
  exposures are stratum means — which is what makes the model a mean-field
  approximation.

Local life table
  The country's own UN {term}`WPP` period life table, used for
  `delta_yll_local_total`. Answers "years under current local mortality".

Standard life table
  GBD's theoretical minimum-risk reference life table, identical across
  countries, used for `delta_yll_standard_total`. Answers "years of potential
  life", and is the right anchor for comparison with published GBD estimates.

Population mode
  A whole-country **annual** ΔYLL, if everyone ate the meal daily. Units are
  years per year.

Individual modes
  `median` and `age`: expected change in one person's **remaining-lifetime**
  YLL. Units are years per person. Not comparable with population mode.

GBD
  Global Burden of Disease, the IHME study that supplies the relative-risk
  curves, exposure estimates and reference life table.

GHE
  WHO's Global Health Estimates, the source of cause-specific mortality rates.

GDD-IA
  Global Dietary Database for Impact Assessments (Springmann 2026), the source
  of the per-country calorie anchor.

WPP
  UN World Population Prospects, the source of population by age and sex and of
  the local life tables.

EPA + DHA
  Eicosapentaenoic and docosahexaenoic acid, the long-chain omega-3 fatty acids
  found in seafood. This is what `seafood_omega3_mg` means; it excludes the
  plant omega-3 ALA.
```
