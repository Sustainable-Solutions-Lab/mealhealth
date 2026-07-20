<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Licensing and citation

The short version: the code is GPL, the bundled data is not, and the
combination is **non-commercial**. If you are redistributing mealhealth,
building on it commercially, or publishing results from it, read on.

## What is licensed how

- **Source code:** GPL-3.0-or-later.
- **Documentation** (`docs/`, `README.md`): CC-BY-4.0.
- **Bundled data:** governed as a whole by
  `LICENSES/LicenseRef-MealHealth-NonCommercial-Data.txt`. The binding
  restriction is **non-commercial**, and it comes from **IHME GBD** — the
  relative risks, reference life table, and nutrient and mediator exposures are
  under the IHME Free-of-Charge Non-commercial User Agreement. WHO mortality is
  governed separately by the [WHO dataset
  terms](https://www.who.int/about/policies/publishing/data-policy/terms-and-conditions),
  which permit redistribution for public-health purposes with attribution. The
  other components are more permissive: UN WPP is CC BY 3.0 IGO, and the
  GDD-IA-derived diet data is CC BY 4.0 (attribution-only).

**Consequence:** although the code is GPL, the distributed package *as a whole*
(code + bundled data) is for **non-commercial research, teaching and private
study, with attribution**. The GPL covers the code and does not grant
commercial-use or unrestricted-redistribution rights over the bundled data.
Commercial users must obtain the underlying IHME GBD data under an appropriate
licence and regenerate the data themselves with
[`tools/build_data.py`](../development/data_build.md).

## Points to flag

1. **IHME GBD raw data are not redistributable.** Only reduced, adapted
   derivatives are shipped. Whether these fall within "adapted use" rather than
   "redistribution" under the IHME agreement is a judgment call; a downstream
   user needing certainty should regenerate the data from their own licensed
   copies.
2. **GPL code + non-commercial data is an intentional but unusual combination.**
   The GPL cannot apply to the data files (it would imply freedoms the IHME
   terms forbid); hence the separate `LicenseRef` on the data. Redistributors
   must keep both notices.
3. **The baseline diet derives from GDD-IA, which is CC BY 4.0.** It imposes no
   restriction beyond attribution to Springmann (2026) — the non-commercial
   restriction on the bundled data comes from IHME GBD alone.
4. **Attribution to preserve when publishing:** IHME GBD, WHO GHE and the
   represented source countries, UN WPP (CC BY 3.0 IGO), and GDD-IA (Springmann
   2026).

## WHO attribution

World Health Organization. *Global Health Estimates 2021: Deaths by Cause, Age,
Sex, by Country and by Region, 2000–2021*. Geneva: World Health Organization;
2024. Accessed 15 July 2026. The `source_country` column in `mortality.csv`
identifies and acknowledges the WHO source country used for every record. The
table was extracted and processed by mealhealth as described in
[Data sources](data_sources.md); neither WHO nor the represented countries
endorse mealhealth or its analyses.

## Citing the data

When publishing results, cite:

- Global Burden of Disease Collaborative Network, *GBD 2023 Results* and *GBD
  2023 Burden of Proof*, IHME — <https://vizhub.healthdata.org/gbd-results/> and
  <https://vizhub.healthdata.org/burden-of-proof/> (relative-risk age structure
  derived from GBD 2019 Relative Risks).
- Global Burden of Disease Collaborative Network, *GBD 2023 Risk Exposure
  Estimates 1990–2023*, IHME, 2025.
- Global Burden of Disease Collaborative Network, *GBD 2023 Demographics
  1950–2023*, IHME —
  <https://ghdx.healthdata.org/record/ihme-data/gbd-2023-demographics-1950-2023>.
- World Health Organization, *Global Health Estimates 2021: Deaths by Cause,
  Age, Sex, by Country and by Region, 2000–2021*. Geneva: WHO; 2024. Accessed
  15 July 2026. Used under the [WHO dataset
  terms](https://www.who.int/about/policies/publishing/data-policy/terms-and-conditions);
  source countries are identified by `source_country` in the bundled table.
- United Nations, *World Population Prospects* — <https://population.un.org/wpp/>.
- Springmann, M. *Global dietary estimates for conducting health, environmental
  and economic impact assessments.* Nature Food (2026),
  [doi:10.1038/s43016-026-01388-z](https://doi.org/10.1038/s43016-026-01388-z);
  dataset Zenodo
  [10.5281/zenodo.20818140](https://doi.org/10.5281/zenodo.20818140) (GDD-IA —
  the baseline dietary intakes).
- Bechthold et al. 2019; Li et al. 2024; Chan et al. 2011 (red-meat relative
  risks).

## Citing the software

`CITATION.cff` in the repository root carries the machine-readable citation
metadata; GitHub renders it as a "Cite this repository" button, and most
reference managers can import it directly. Cite the software *in addition to*
the data sources above, never instead of them — the substantive scientific
content is theirs.
