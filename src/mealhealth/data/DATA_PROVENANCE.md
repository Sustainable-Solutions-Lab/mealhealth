<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Bundled data — schemas and provenance

These CSVs are processed/adapted derivatives. The health/demographic files are
produced by `tools/prepare_data.py` from public raw datasets (WHO GHE, IHME GBD,
UN WPP);
the baseline-diet files are a separate dataset, while the nutrient and mediator
baselines are built directly from GBD risk exposure (and WPP for the aggregated
nutrient baseline; see `docs/data_sources.md`).
See `docs/data_sources.md` for sources and licensing (non-commercial).
Reference year: mortality/population 2020; life table 2024 (nearest available in
the UN WPP abridged file); intake circa 2018–2020.

## `relative_risks.csv`
GBD 2023 Burden-of-Proof dietary dose–response curves, in the model fresh/dry
basis.
`risk_factor, cause, age, exposure_g_per_day, rr_mean, rr_low, rr_high`
- 8 risk factors × their mapped causes × 15 adult age bands (25–29 … 95+).
  `nuts_seeds` maps to CHD only (no T2DM in GBD 2023); `processed_meat` to
  CHD/T2DM/CRC (no stroke); `red_meat` uses a literature log-linear override.
- The age-aggregated BoP curve is age-expanded via a curated multiplicative
  log-RR attenuation table and clipped at the curated TMREL; each curve is then
  thinned to ≤40 exposure knots (the model interpolates log-linearly).
- Meat exposures are converted to fresh retail basis (×1.43 from cooked).
- Seafood omega-3 is EPA + DHA in g/day, maps to CHD only, and is clipped at
  the midpoint of its 0.470–0.660 g/day TMREL range.

## `baseline_intake.csv`
Per-country baseline daily intake per risk-factor group (model basis).
`country, risk_factor, intake_g_per_day`
- `red_meat` (unprocessed) and `processed_meat` are split via the GDD-IA
  processed-meat fraction; their sum is the combined red-meat intake.
- GDD-IA = Global Dietary Database for Impact Assessments (Springmann 2026,
  doi:10.1038/s43016-026-01388-z; data CC-BY-4.0 at doi:10.5281/zenodo.20818140).

## `baseline_calories.csv`
`country, kcal_per_day` — total baseline daily dietary energy (GDD-IA all-food
groups total).

## `baseline_nutrients.csv`
Per-country GBD 2023 adult seafood omega-3 exposure, population-weighted over
the 15 adult age groups and both sexes with WPP 2020 weights.
`country,nutrient,intake_g_per_day,source_country,source_year`
- `nutrient=omega3` means seafood EPA + DHA in g/day.
- All 175 countries have exactly one row. French Guiana uses the sole proxy,
  `source_country=FRA`; every other row uses its own country.
- Built by `tools/build_baseline_nutrients_from_gbd.py` from the pinned dietary
  file in GBD 2023 Risk Exposure Estimates 1990–2023 (SHA-256
  `4e80f1047b13251d674da636d6cce35cb56b64878e79774c59f927d569d9b28f`)
  and UN WPP population data.

## `baseline_mediators.csv`
GBD 2023 urinary-sodium and systolic-blood-pressure exposure by country, adult
age group, and sex in 2020.
`country,age,sex,sodium_urinary_g_per_day_mean,sodium_urinary_g_per_day_lower,sodium_urinary_g_per_day_upper,sbp_mmhg_mean,sbp_mmhg_lower,sbp_mmhg_upper,source_country,source_year`
- All 175 countries have 15 adult ages × two sexes. French Guiana uses the sole
  proxy, `source_country=FRA`; every other row uses its own country.
- The `lower` and `upper` values are marginal uncertainty bounds on the GBD
  modeled stratum mean. They are not within-stratum quantiles and do not supply
  a usual-SBP standard deviation. The runtime uses the means only; a
  future distributional mediator would require additional input.
- Built by `tools/build_baseline_mediators_from_gbd.py` from the pinned high-
  sodium (`0ea88321…`) and high-SBP (`dd317224…`) files in GBD 2023 Risk
  Exposure Estimates 1990–2023.

## `sodium_relative_risks.csv`
Current all-age GBD 2023 Burden-of-Proof curves for the sodium mediator.
`path,curve_cause,exposure,rr_mean,rr_low,rr_high,risk_lower,risk_upper,star_rating,rei_id,cause_id`
- `path=sodium`: urinary sodium → stomach cancer.
- `path=sbp`: systolic blood pressure → CHD, combined stroke, and CKD.
- Built from the public BoP API by `tools/build_sodium_relative_risks.py`.
  The runtime uses `rr_mean`; bounds and metadata are retained for provenance.
  SHA-256: `3261d4d230e1f7370c30c9e6d2922a0bc5c5851c8b57589e23df485caa2c0850`.

## `sbp_age_attenuation.csv`
`curve_cause,age,beta` — multiplicative log-RR age shape for the three SBP
curves, normalized to 1 at age 60–64. Built once from the GBD 2019 RR workbook
by `tools/generate_sbp_age_attenuation.py`; this is a transparent age-shape
donor for the current all-age GBD 2023 curves. SHA-256:
`cc5958d68253207f6bcb65f069e6d065c5a6a456c6d18b7081a14ff066dc20f2`.

## `mortality.csv`
`country,sex,cause,age,source_country,death_rate_per_1000` — WHO Global Health Estimates 2021
cause-specific death rates per 1,000 person-years, year 2020. The seven model
causes are CHD, ischemic stroke, haemorrhagic stroke, diabetes mellitus,
colorectal cancer, stomach cancer, and chronic kidney disease. The last is the
sum of WHO cause IDs 1272 and 1273. WHO's single `85+` rate is repeated over
the model's `85–89`, `90–94`, and `95+` bands. Five places without a WHO Member
State row use the documented country proxies in `docs/data_sources.md`.
The WHO source country used for each record is retained in `source_country`.
Source attribution: World Health Organization, *Global Health Estimates 2021:
Deaths by Cause, Age, Sex, by Country and by Region, 2000–2021*, Geneva: WHO,
2024; accessed 15 July 2026. Extracted and processed by mealhealth under the
[WHO dataset terms](https://www.who.int/about/policies/publishing/data-policy/terms-and-conditions);
use does not imply endorsement by WHO or by represented countries.
Bundled SHA-256:
`151927d27d29734e565019678aaecc642aaa85dfe463ef91b663649fc54043af`.

## `population.csv`
`age,sex,country,population` — UN WPP male/female population by age band, 2020
(includes a per-sex `all-a` total row).

## `local_life_table.csv`
`country,sex,age,lx,ex` — UN WPP male/female abridged life table, survivors `lx`
(radix 100000) and remaining life expectancy `ex` by age band; per country with
sex-specific World fallback where unavailable.

## `standard_life_table.csv`
`age, ex` — adapted from the GBD 2023 theoretical minimum-risk life table
(TMRLT), published by IHME as
`IHME_GBD_2023_DEMOGRAPHICS_1950_2023_TMRLT_Y2025M06D09.CSV` in the GBD 2023
Demographics 1950–2023 record. The source gives exact-age values through 110;
this runtime derivative retains the 21 age boundaries used by the model through
95. The age-95 value represents the model's final `95+` band. It supplies the
common aspirational remaining life expectancy used for the additional
standard-YLL output.

Countries with complete data across all files: 175.
