<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Data sources and licensing

`mealhealth` bundles small, **processed and adapted** CSVs under
`src/mealhealth/data/`. These are *not* the raw upstream datasets — they are
reduced to the minimum needed to evaluate the health-impact formulas (see
`src/mealhealth/data/DATA_PROVENANCE.md` for exact schemas). The processing is
reproducible from the sibling `food-opt` project via `tools/prepare_data.py`.

## Sources

| Bundled file            | Derived from | Upstream licence |
|-------------------------|--------------|------------------|
| `relative_risks.csv`    | IHME GBD 2019 relative risks (XLSX); red-meat curve from literature meta-analyses via `food-opt` | IHME non-commercial |
| `mortality.csv`         | IHME GBD 2023 cause-specific death rates (2020) | IHME non-commercial |
| `baseline_intake.csv`   | GDD-IA dietary intake; NHANES (USA); GDD-IA processed/red split | GDD non-commercial |
| `baseline_calories.csv` | GDD-IA total dietary energy | GDD non-commercial |
| `population.csv`        | UN World Population Prospects | CC BY 3.0 IGO |
| `life_table.csv`        | UN World Population Prospects abridged life tables | CC BY 3.0 IGO |

### Red-meat relative risk

Carried over from `food-opt`: log-linear curves from Bechthold et al. 2019
(CHD/Stroke), Li et al. 2024 (T2DM) and Chan et al. 2011 (CRC), with GBD
age-attenuation factors. These meta-analyses are calibrated on **unprocessed**
red meat, which is appropriate because processed meat is modelled separately.

### Processed-meat relative risk

Taken directly from the GBD 2019 dose–response curves for "diet high in
processed meat" (CHD/IHD, T2DM, CRC; no stroke), converted to the model's fresh
mass basis.

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
