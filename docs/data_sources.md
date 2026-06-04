<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Data sources and licensing

`mealhealth` bundles small, **processed and adapted** CSVs under
`src/mealhealth/data/`. These are *not* the raw upstream datasets — they are
reduced to the minimum needed to evaluate the health-impact formulas (see
`src/mealhealth/data/DATA_PROVENANCE.md` for exact schemas).

The **health and demographic** data (`relative_risks.csv`, `mortality.csv`,
`population.csv`, `life_table.csv`) is fully reproducible from public source
datasets; `tools/prepare_data.py` then processes them. It uses the **GBD 2023**
vintage throughout: relative risks from the GBD 2023 Burden-of-Proof tool and
mortality from the GBD 2023 Results tool. The **baseline diet**
(`baseline_intake.csv`, `baseline_calories.csv`) is a separate derived dataset —
see [Baseline diet](#baseline-diet) below.

## Sources

| Bundled file            | Derived from | Upstream licence |
|-------------------------|--------------|------------------|
| `relative_risks.csv`    | IHME GBD 2023 Burden-of-Proof dose–response curves (age structure from GBD 2019); red-meat curve from literature meta-analyses | IHME non-commercial |
| `mortality.csv`         | IHME GBD 2023 cause-specific death rates (2020) | IHME non-commercial |
| `population.csv`        | UN World Population Prospects (population by age) | CC BY 3.0 IGO |
| `life_table.csv`        | UN World Population Prospects (abridged life tables) | CC BY 3.0 IGO |
| `baseline_intake.csv`   | Baseline diet dataset (see below) | GDD non-commercial |
| `baseline_calories.csv` | Baseline diet dataset (see below) | GDD non-commercial |

## Obtaining the raw data

Place all raw inputs under `data/raw/` (git-ignored). The UN WPP files and the
GBD 2023 Burden-of-Proof relative-risk curves are downloaded automatically by
`tools/prepare_data.py`; the GBD 2023 cause-specific death-rate CSV requires a
(free) IHME account and must be downloaded manually first.

### 1. IHME GBD 2023 relative risks — Burden of Proof (automatic)

`tools/prepare_data.py` fetches the age-aggregated dietary exposure–response
curves from the IHME Burden-of-Proof tool
(<https://vizhub.healthdata.org/burden-of-proof/>) and caches them at
`data/raw/bop_rr_curves.csv`. **No login is required** — the JSON endpoints sit
behind Cloudflare's edge bot-check only, which a normal browser User-Agent
passes. (Automated cloud IPs may get a 403; in that case run the tool once from a
normal machine — the curves cache and are reused thereafter.)

The Burden-of-Proof tool serves only an age-aggregated ("All Ages") curve per
risk–cause pair. The per-age structure is restored at build time from a curated
multiplicative log-RR **age-attenuation** table
(`tools/reference/rr_age_attenuation.csv`), and each curve is clipped at a
curated **TMREL** (`tools/reference/rr_tmrel.csv`, GBD 2023 appendix Table 18).
The age-attenuation table is produced once by
`tools/generate_rr_age_attenuation.py` from the GBD 2019 relative-risk workbook
(GBD's documented 60-64 reference age, the only remaining use of GBD 2019). To
rebuild it, download *"Relative risks: all risk factors except for ambient air
pollution, alcohol, smoking, and temperature [XLSX]"* from
<https://ghdx.healthdata.org/record/ihme-data/gbd-2019-relative-risks> (free IHME
account) and save it, unrenamed, as
`data/raw/IHME_GBD_2019_RELATIVE_RISKS_Y2020M10D15.XLSX`.

### 2. IHME GBD 2023 cause-specific death rates (manual)

Go to the GBD Results Tool <https://vizhub.healthdata.org/gbd-results/> and sign
in. Reproduce this query (a permalink configured for 2020 is
`https://vizhub.healthdata.org/gbd-results?params=gbd-api-2023-permalink/ab3e7b526315599bf5cabbfe6c34e104`):

- **GBD estimate:** Cause of death or injury
- **Measure:** Deaths · **Metric:** Rate (per 100,000)
- **Cause:** Ischemic heart disease, Ischemic stroke, Diabetes mellitus, Colon
  and rectum cancer (Chronic respiratory diseases / All causes optional — they
  are ignored)
- **Location:** all countries and territories
- **Age:** the full individual age range (`<1 year`, `12-23 months`,
  `2-4 years`, `5-9 years`, … `95+ years`)
- **Sex:** Both · **Year:** 2020

Export as CSV and save as `data/raw/IHME-GBD_2023-death-rates-2020.csv`.

### 3. UN World Population Prospects (automatic)

`tools/prepare_data.py` downloads these into `data/raw/` if absent (WPP2024,
medium variant):

- Population by 5-year age group → `WPP_population.csv.gz`
- Abridged life table → `WPP_life_table.csv.gz`

### Red-meat relative risk

The red-meat dose–response curve is not from a downloadable dataset: it is a
small curated table of log-linear curves from literature meta-analyses, bundled
at `tools/reference/red_meat_rr_log_linear.csv` (Bechthold et al. 2019 for
CHD/Stroke, Li et al. 2024 for T2DM, Chan et al. 2011 for CRC), age-attenuated
using the curated age-attenuation table. The Burden-of-Proof red-meat curve is
used only for its exposure grid (the override is evaluated on it). These
meta-analyses are calibrated on **unprocessed** red meat, which is appropriate
because processed meat is modelled separately.

### Processed-meat relative risk

Taken directly from the GBD 2023 Burden-of-Proof dose–response curves for "diet
high in processed meat" (CHD/IHD, T2DM, CRC; no ischemic stroke curve),
converted to the model's fresh mass basis and age-expanded like the other curves.

## Baseline diet

`baseline_intake.csv` and `baseline_calories.csv` give the per-country baseline
diet (GDD-IA / NHANES intakes, with the unprocessed/processed red-meat split
from the GDD-IA processed fraction). Unlike the health data, this is a *derived
research product* rather than a public raw download.

> **Temporary provenance.** The committed baseline-diet CSVs are currently
> produced from the sibling **GLADE** project (the Global Land, Agriculture, Diet
> and Emissions model, formerly `food-opt`; openly available during development)
> via `tools/baseline_diet_from_glade.py`. They will be published as a standalone
> dataset on **Zenodo**, after which `mealhealth` will fetch them from there and
> that tool will be retired. Until then the committed CSVs are the canonical
> artifacts and do not need regenerating.

## Licensing summary (important)

* **Source code:** GPL-3.0-or-later.
* **Documentation** (`docs/`, `README.md`): CC-BY-4.0.
* **Bundled data:** non-commercial. The GBD (IHME) and GDD (Tufts) terms are
  **non-commercial, no-redistribution-of-raw-data**; only adapted, minimal
  derivatives are shipped here. UN WPP is CC BY 3.0 IGO. The combined bundled
  data is governed by `LICENSES/LicenseRef-MealHealth-NonCommercial-Data.txt`.

**Consequence:** although the code is GPL, the distributed package *as a whole*
(code + bundled data) is for **non-commercial research, teaching and private
study only, with attribution**. The GPL applies to the code and does **not**
grant commercial-use or unrestricted-redistribution rights over the bundled
data. Commercial users must obtain the underlying GBD/GDD data under appropriate
licences and regenerate the data themselves.

## Potential licence concerns to flag

1. **GBD / GDD raw data are not redistributable.** We ship only reduced,
   adapted derivatives. Whether these specific derivatives fall within "adapted
   use" rather than "redistribution" under the IHME/GDD agreements is a judgment
   call; a conservative downstream user who needs certainty should regenerate
   the data from their own licensed copies using `tools/prepare_data.py`.
2. **GPL + non-commercial data is an intentional but unusual combination.** The
   GPL cannot be applied to the data files (it would imply freedoms the upstream
   terms forbid); hence the separate `LicenseRef` on the data. Redistributors
   must keep both notices.
3. **UN WPP attribution** (CC BY 3.0 IGO) must be preserved when results are
   published.

## Citation

When publishing results, cite:

* Global Burden of Disease Collaborative Network, GBD 2023 Results and GBD 2023
  Burden of Proof, IHME — https://vizhub.healthdata.org/gbd-results/ and
  https://vizhub.healthdata.org/burden-of-proof/ (relative-risk age structure
  derived from GBD 2019 Relative Risks)
* Global Dietary Database, Tufts University —
  https://www.globaldietarydatabase.org/
* United Nations, World Population Prospects —
  https://population.un.org/wpp/
* Bechthold et al. 2019; Li et al. 2024; Chan et al. 2011 (red-meat RR).
