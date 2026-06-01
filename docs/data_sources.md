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
datasets that a developer downloads themselves; `tools/prepare_data.py` then
processes them. The **baseline diet** (`baseline_intake.csv`,
`baseline_calories.csv`) is a separate derived dataset — see
[Baseline diet](#baseline-diet) below.

## Sources

| Bundled file            | Derived from | Upstream licence |
|-------------------------|--------------|------------------|
| `relative_risks.csv`    | IHME GBD 2019 relative risks (XLSX); red-meat curve from literature meta-analyses | IHME non-commercial |
| `mortality.csv`         | IHME GBD 2023 cause-specific death rates (2020) | IHME non-commercial |
| `population.csv`        | UN World Population Prospects (population by age) | CC BY 3.0 IGO |
| `life_table.csv`        | UN World Population Prospects (abridged life tables) | CC BY 3.0 IGO |
| `baseline_intake.csv`   | Baseline diet dataset (see below) | GDD non-commercial |
| `baseline_calories.csv` | Baseline diet dataset (see below) | GDD non-commercial |

## Obtaining the raw data

Place all raw inputs under `data/raw/` (git-ignored). The two UN WPP files are
public and downloaded automatically by `tools/prepare_data.py`; the two IHME GBD
files require a (free) IHME account and must be downloaded manually first.

### 1. IHME GBD 2019 relative risks (manual)

Go to <https://ghdx.healthdata.org/record/ihme-data/gbd-2019-relative-risks>.
Under the **Files** tab, download *"Relative risks: all risk factors except for
ambient air pollution, alcohol, smoking, and temperature [XLSX]"* (log in with
your IHME account when prompted). Save it, unrenamed, as
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
using the GBD red-meat curve's age structure. These meta-analyses are calibrated
on **unprocessed** red meat, which is appropriate because processed meat is
modelled separately.

### Processed-meat relative risk

Taken directly from the GBD 2019 dose–response curves for "diet high in
processed meat" (CHD/IHD, T2DM, CRC; no stroke), converted to the model's fresh
mass basis.

## Baseline diet

`baseline_intake.csv` and `baseline_calories.csv` give the per-country baseline
diet (GDD-IA / NHANES intakes, with the unprocessed/processed red-meat split
from the GDD-IA processed fraction). Unlike the health data, this is a *derived
research product* rather than a public raw download.

> **Temporary provenance.** The committed baseline-diet CSVs are currently
> produced from the sibling `food-opt` project (openly available during
> development) via `tools/baseline_diet_from_foodopt.py`. They will be published
> as a standalone dataset on **Zenodo**, after which `mealhealth` will fetch
> them from there and that tool will be retired. Until then the committed CSVs
> are the canonical artifacts and do not need regenerating.

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

* Global Burden of Disease Collaborative Network, GBD 2019 Relative Risks and
  GBD 2023 Results, IHME — https://vizhub.healthdata.org/gbd-results/
* Global Dietary Database, Tufts University —
  https://www.globaldietarydatabase.org/
* United Nations, World Population Prospects —
  https://population.un.org/wpp/
* Bechthold et al. 2019; Li et al. 2024; Chan et al. 2011 (red-meat RR).
