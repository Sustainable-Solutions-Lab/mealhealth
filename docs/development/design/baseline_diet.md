<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Baseline diet design

:::{note}
Written while the independent baseline was being built; its "feature branch"
status line is historical. The contract it describes is the one that ships.
[Data sources](../../model/data_sources.md) is the current description.
:::

Status: implemented on the feature branch for the independent baseline.

This document records the implemented baseline contract. The canonical direct
table is built from official GBD 2023 exposure files; the calorie anchor is
built from public GDD-IA and WPP files; sodium/SBP remains a separate
stratum-resolved mediator table. No sibling checkout or nutrient-only legacy
builder is part of the workflow.

## Canonical inputs and outputs

`tools/reference/baseline_country_sources.csv` defines the fixed 175-country
target set and explicit source proxies:

```text
country,gbd_exposure_source_country,calorie_source_country
AFG,AFG,IRN
GUF,FRA,FRA
USA,USA,USA
```

`tools/dietary_exposure_sources.py` owns the pinned filenames, SHA-256 hashes,
units, age mapping, WPP weighting, country-name mapping, and basis factors.

`tools/build_baseline_exposure.py` writes:

```text
country,risk_factor,exposure_g_per_day,source_country,source_year
```

It produces exactly 175 × 8 rows for fruits, vegetables, whole grains, legumes,
nuts and seeds, red meat, processed meat, and seafood EPA+DHA. Values are 2020
GBD central means weighted over the 15 adult age groups and both sexes with WPP
2020 population. The runtime evaluates dose-response curves at these country
means; it does not reconstruct a full GBD exposure distribution or PAF.

`tools/build_baseline_calories.py` writes one row per target country. It selects
GDD-IA `type=prim`, `food_group=all-fg`, `sex=BTH`, `residence=all-u`, `stats=mean`
for 2020 and age bands 20–39, 40–64, and 65+, then reweights those bands to
ages 25+ with WPP 2020 population.

`tools/build_baseline_mediators_from_gbd.py` writes exactly 175 × 15 × 2 rows
for urinary sodium and SBP. It uses the same target manifest and retains the
country-age-sex means and uncertainty bounds needed by `SodiumMeanShiftModel`.
Sodium remains opt-in through `sodium_mg=None` versus an explicit numeric value.

## Basis decisions

- Fruits and vegetables use fresh/as-eaten grams.
- Whole grains, legumes, and nuts/seeds use dry grams; legumes use the 0.40
  cooked-to-dry factor when converting the native GBD axis.
- Red meat uses fresh raw retail grams; the 1.43 cooked-to-raw conversion is
  applied consistently to its exposure axis.
- Processed meat uses as-eaten product grams. It is a separate GBD factor and
  receives no unsupported universal raw-retail conversion.
- Seafood omega-3 is EPA+DHA in g/day and is included in the direct table but
  activated in assessments only when `seafood_omega3_mg` is supplied.

## Runtime contract

`mealhealth.data.baseline_exposure()` strictly validates schema, complete
country-factor coverage, finite non-negative values, 2020 provenance, and the
French Guiana → France exposure proxy. All other bundled loaders use its
validated country set. `CountryBurden` loads all eight direct baselines from
this table; mediator data are loaded separately only for sodium assessments.

The superseded reconciliation and nutrient-only path are intentionally absent;
they are not regeneration or runtime paths.

## Reproduction and validation

Stage the authenticated GBD exposure files under `data/raw/`, place the public
GDD-IA calorie CSV under `data/raw/`, and run:

```bash
uv run python -m tools.build_data
uv run pytest -q
uv run ruff check .
uv run --group docs sphinx-build -b html docs /tmp/mealhealth-docs
```

The committed tables are deterministic derivatives. Raw IHME files are not
redistributed; users regenerating them must comply with the applicable IHME
non-commercial terms and retain the source attribution documented in
`docs/model/data_sources.md`.
