<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Data sources

`mealhealth` bundles small, **processed and adapted** CSVs under
`src/mealhealth/data/`. These are not the raw upstream datasets: each is reduced
to the minimum needed to evaluate the health-impact formulas. This page
documents where each number comes from. Exact column schemas are in
`src/mealhealth/data/DATA_PROVENANCE.md`, terms of use in
[Licensing and citation](licensing.md), and the regeneration workflow in
[Rebuilding the bundled data](../development/data_build.md).

## What is bundled

| Bundled file              | Built from | Upstream terms |
|---------------------------|------------|----------------|
| `relative_risks.csv`      | IHME GBD 2023 Burden-of-Proof dose–response curves (age structure from GBD 2019); red-meat curve from literature meta-analyses | IHME non-commercial |
| `mortality.csv`           | WHO Global Health Estimates 2021 cause-specific death rates (2020) | Custom WHO dataset terms for public-health use; redistribution permitted with attribution |
| `standard_life_table.csv` | IHME GBD 2023 theoretical minimum-risk life table | IHME non-commercial |
| `baseline_exposure.csv`   | Seven food-group + seafood omega-3 files from IHME GBD 2023 Risk Exposure Estimates 1990–2023 + UN WPP weights | IHME non-commercial / CC BY 3.0 IGO |
| `baseline_mediators.csv`  | High-sodium and high-SBP files from IHME GBD 2023 Risk Exposure Estimates 1990–2023 | IHME non-commercial |
| `sodium_relative_risks.csv` | IHME GBD 2023 Burden-of-Proof sodium and SBP curves | IHME non-commercial |
| `sbp_age_attenuation.csv` | GBD 2019 relative-risk workbook age shape | IHME non-commercial |
| `population.csv`          | UN World Population Prospects (population by age) | CC BY 3.0 IGO |
| `local_life_table.csv`    | UN World Population Prospects (abridged life tables) | CC BY 3.0 IGO |
| `baseline_calories.csv`   | GDD-IA 2020 all-food calorie target + WPP age weights | CC BY 4.0 |

Reference years: mortality and population 2020, exposure 2020, life tables the
nearest available UN WPP abridged year (2024), intake circa 2018–2020.

## Relative-risk curves

The dose–response curves come from the IHME Burden-of-Proof tool
(<https://vizhub.healthdata.org/burden-of-proof/>), fetched from its public JSON
endpoints and cached at `data/raw/bop_rr_curves.csv`.

The tool serves only an age-aggregated ("All Ages") curve per risk–cause pair.
Three curated tables under `tools/reference/` restore the rest:

- **Age structure.** `rr_age_attenuation.csv` holds a multiplicative log-RR
  attenuation, normalised to GBD's 60–64 reference age, that re-expands each
  curve across the 15 adult age bands. It derives from the GBD 2019
  relative-risk workbook — the only remaining use of GBD 2019 in the dietary
  curves.
- **Plateau.** `rr_tmrel.csv` (GBD 2023 appendix Table 18) gives the TMREL at
  which each curve is clipped, so intake past the plateau yields no further
  effect.
- **Red-meat override.** `red_meat_rr_log_linear.csv` supplies log-linear
  red-meat curves from literature meta-analyses (Bechthold et al. 2019 for
  CHD/stroke, Li et al. 2024 for type 2 diabetes, Chan et al. 2011 for
  colorectal cancer). These are calibrated on **unprocessed** red meat, which is
  the right basis because processed meat is modelled separately. The
  Burden-of-Proof red-meat curve is used only for its exposure grid.

Processed meat is taken directly from its own GBD 2023 Burden-of-Proof curves
(CHD, type 2 diabetes, colorectal cancer; there is no ischemic-stroke curve),
kept on its native as-eaten product basis and age-expanded like the others.

## Cause-specific mortality

Male and female age-specific death rates for 2020, queried from the public
[WHO Global Health Estimates 2021
dataset](https://www.who.int/data/global-health-estimates/) through the [GHO
OData interface](https://www.who.int/data/gho/info/gho-odata-api).

The model uses WHO cause IDs 640 (stomach cancer), 650 (colon and rectum
cancers), 800 (diabetes mellitus), 1130 (ischaemic heart disease), 1141
(ischaemic stroke), 1142 (haemorrhagic stroke), and 1272 + 1273 (the two
chronic-kidney categories, summed).

Several compromises follow from what WHO publishes: broad diabetes mortality
stands in for type 2, the open `85+` band is repeated across three model strata,
and five territories use documented proxy countries. Aortic aneurysm and
peripheral arterial disease have no standalone WHO rates, so those two sodium
pathways are dropped. [Limitations](limitations.md#burden-data-compromises)
spells out what each of these costs.

See WHO's [cause-of-death
methods](https://cdn.who.int/media/docs/default-source/gho-documents/global-health-estimates/ghe2021_cod_methods.pdf).
The cached raw table is not bundled in the package; the `source_country` column
in `mortality.csv` identifies the WHO source country for every record.

## Reference life table

The GBD 2023 theoretical minimum-risk life table gives remaining life
expectancy at exact ages 0 to 110. The builder validates it and keeps the 21
boundary values for the model's abridged bands from `<1` through `95+`, with the
final band using the age-95 value. This is the aspirational life table behind
the standardised YLL output.

## Population and local life tables

Both come from UN World Population Prospects (WPP2024, medium variant):
population by five-year age group, and the abridged life table. These supply the
population weights used throughout and the local remaining life expectancy
behind `delta_yll_local_total`.

## Baseline exposure

`baseline_exposure.csv` is the canonical per-country baseline diet, built
directly from the eight GBD 2023 risk-exposure files (seven food groups plus
seafood omega-3). The builder selects 2020 and the 15 adult age groups,
identifies national GBD locations through the public location hierarchy, and
weights every age–sex exposure cell by WPP 2020 male and female population
(WPP's 95–99 and 100+ groups fold into GBD's 95+).

The location hierarchy matters because the bulk exposure files also contain
subnational rows whose names can collide with country names. Mortality data is
not used for location selection.

Output is mean exposure in g/day. Uncertainty bounds are validated but not
aggregated, because the model does not propagate exposure uncertainty. All 175
countries are direct except French Guiana, which uses the documented `GUF → FRA`
proxy.

## Sodium mediator baseline

`baseline_mediators.csv` joins 2020 urinary-sodium and high-SBP exposure at
country × adult age × sex resolution, retaining each modelled stratum mean and
its marginal uncertainty bounds.

Those bounds quantify uncertainty in the mean. They are not exposure quantiles
across people and cannot supply the within-stratum usual-SBP standard deviation
that a distributional model would need. The model evaluates risk at the stratum
mean; the bounds are retained for provenance only.

## Sodium and SBP relative risks

Four current GBD 2023 Burden-of-Proof curves from the public API: sodium →
stomach cancer, and SBP → ischemic heart disease, combined stroke, and chronic
kidney disease. Units and evidence-star metadata are validated, and the all-age
mean with pointwise bounds is written to `sodium_relative_risks.csv`.

`sbp_age_attenuation.csv` extracts per-age log-RR shapes from the same GBD 2019
relative-risk workbook used for the dietary attenuation, normalised at age
60–64. The combined-stroke age shape is applied to both WHO stroke categories,
and the CKD donor is CKD due to type 2 diabetes.

### The sodium-to-SBP response

The reviewed response coefficients are pinned in
`tools/reference/sodium_to_sbp.json`, retaining published native units beside
the canonical mm Hg per g/day urinary-sodium values. The primary response is
from Filippini et al. (2021) — the pinned slope of 2.42 mm Hg per g/day urinary
sodium that the shipped model uses. Transport sensitivities from Huang et al.
(2020), Mozaffarian et al. (2014) and the Filippini hypertension subgroups are
documented for future use but do not enter the central result.

## Calorie baseline

`baseline_calories.csv` is built from the public GDD-IA 2020 all-food calorie
table, using its `all-fg`, `BTH`, `all-u`, 2020 mean rows for age bands 20–39,
40–64 and 65+, reweighted to ages 25+ with WPP. The checked-in source manifest
(`tools/reference/baseline_country_sources.csv`) pins the 175-country target set
and every calorie source proxy.

**GDD-IA** — the *Global Dietary Database for Impact Assessments* — is a
per-country dietary-intake dataset for integrated-assessment use, developed by
**Marco Springmann** (University College London). It combines regional food
availability and food-waste estimates, socio-demographic variation in survey
intake, and energy-intake estimates based on measurements of body weight, height
and physical activity, into complete diets whose absolute intake levels are
comparable across regions. It is also the baseline diet used by the EAT–Lancet
2.0 commission.

GDD-IA is published and openly licensed under CC BY 4.0:

- Paper — Springmann, M. *Global dietary estimates for conducting health,
  environmental and economic impact assessments.* Nature Food (2026),
  [doi:10.1038/s43016-026-01388-z](https://doi.org/10.1038/s43016-026-01388-z)
- Dataset — Zenodo [10.5281/zenodo.20818140](https://doi.org/10.5281/zenodo.20818140)
  (1990–2020 in five-year steps, downloadable without an account)

Attribution under CC BY 4.0 suffices; no separate permission is needed.

## Validation at the boundary

JSON returned by the IHME and WHO APIs is checked against strict Pydantic
schemas in `tools/source_schemas.py` the moment it arrives. Subsequent dataframe
checks enforce model-specific units, coverage, ordering and completeness, and
every manually staged GBD file is verified against a pinned SHA-256. The intent
is that a silently changed upstream file stops the build rather than shifting
the bundled numbers.
