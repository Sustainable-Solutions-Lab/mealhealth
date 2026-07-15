<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Bundled data — schemas and provenance

These CSVs are processed/adapted derivatives. The health/demographic files are
produced by `tools/prepare_data.py` from public raw datasets (IHME GBD, UN WPP);
the baseline-diet files are a separate dataset, while the nutrient baseline is
built directly from GBD dietary-risk exposure and WPP (see
`docs/data_sources.md`).
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

## `mortality.csv`
`age, cause, country, death_rate_per_1000` — GBD cause-specific death rate per
1,000 person-years, year 2020, causes CHD/Stroke/T2DM/CRC.

## `population.csv`
`age, country, population` — UN WPP population by age band, 2020 (includes the
`all-a` total row).

## `local_life_table.csv`
`country, age, lx, ex` — UN WPP abridged life table (both sexes), survivors
`lx` (radix 100000) and remaining life expectancy `ex` by age band; per country
with World fallback where unavailable.

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
