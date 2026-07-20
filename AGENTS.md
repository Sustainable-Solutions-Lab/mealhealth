<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Developer notes (AGENTS.md / CLAUDE.md)

## What this is

`mealhealth` is a small, installable Python package that turns a meal (in
food-group terms + calories) into a change in years of life lost, using GBD 2023
relative-risk curves and a per-country baseline diet.

## Layout

```
src/mealhealth/
  foodgroups.py   # risk-factor groups, causes, age buckets, mass basis
  data.py         # cached loaders for bundled CSVs
  model.py        # calculation engine (curves, burden, substitution, modes)
  api.py          # public assess_meal() and helpers
  data/*.csv      # bundled processed data (+ DATA_PROVENANCE.md)
tools/build_data.py                # bundled-data regeneration workflow
tools/dietary_exposure_sources.py # shared GBD exposure/source contract
tools/prepare_data.py              # internal health/demographic build stage
tools/build_baseline_exposure.py  # internal GBD/WPP direct-baseline stage
tools/build_baseline_calories.py  # internal GDD-IA/WPP calorie-baseline stage
tools/build_baseline_mediators_from_gbd.py # internal sodium/SBP baseline stage
tools/generate_rr_age_attenuation.py # one-off: curated RR age-attenuation table from GBD 2019
tools/reference/*.csv              # curated regeneration inputs (red-meat RR, TMREL, age attenuation)
tests/                  # pytest suite
docs/                   # Sphinx site: conf.py + Markdown pages (MyST), built with furo
```

## Key design decisions

* **Per-country.** The model works at the country level directly — there is no
  optimisation or country clustering here.
* **Current burden inputs.** Relative-risk curves come from the GBD 2023
  Burden-of-Proof tool (age-aggregated; fetched without login), age-expanded via
  a curated attenuation table (GBD 2019 age shape, normalized to the 60-64
  reference age) and clipped at curated TMRELs. Mortality is WHO GHE 2021,
  using its 2020 country-age-sex rates.
* **Direct curve evaluation.** RR is read off the curve by log-linear
  interpolation.
* **Relative to baseline.** PAF is `1 − RR(x)/RR(x_base)`; the PAF carries no
  TMREL term — the TMREL only shapes where each bundled curve plateaus.
* **Processed meat is separate** from red meat (its own GBD 2023 curve; the
  baseline split comes from the GDD-IA processed fraction).
* **Mass basis** reconciles GBD's native exposure bases with measured intakes;
  the meal input basis is documented per group in `docs/food_groups.md`.
* **Optional nutrient factors are separate from food groups.** They use explicit
  API keywords in mg, convert to the engine's g/day axis, and are excluded when
  omitted (`None`) but included when explicitly supplied as `0.0`.

## Dev workflow

Use [uv](https://docs.astral.sh/uv/). The first `uv run` sets up the environment
and installs the project plus the `dev` dependency group (defined in
`pyproject.toml`).

```bash
uv run pytest -q
uv run mypy
uv run ruff format . && uv run ruff check .
uv run reuse lint
uv run --group docs sphinx-build -b html docs docs/_build/html   # build the docs site
```

Dev and docs tooling live in PEP 735 `[dependency-groups]`, not in published
extras. The docs site (Sphinx + MyST + furo) is deployed to GitHub Pages by
`.github/workflows/docs.yml` on pushes to `master`, once Pages is enabled for
the repo.

## Regenerating bundled data

Regenerate bundled data with the command below. See `docs/data_sources.md` for
what to download into `data/raw/`; the UN WPP files, WHO mortality, location
hierarchy, and public GBD Burden-of-Proof curves download automatically:

```bash
uv run python -m tools.build_data
```

The command runs the direct exposure baseline, calorie baseline, health and
demographic data, sodium mediator baseline, and sodium/SBP curve stages in the
required order. The RR age structure and TMRELs are read from curated tables
under `tools/reference/`. The two `generate_*_age_attenuation.py` tools update
curated reference tables when their source workbook is deliberately refreshed.

The direct baseline (`baseline_exposure.csv`) is built from the seven dietary
food-group files plus seafood EPA+DHA in the official GBD 2023 Risk Exposure
Estimates, using WPP population weights. `baseline_calories.csv` is built from
the public GDD-IA 2020 calorie table and WPP weights. The checked-in source
manifest under `tools/reference/` pins the 175-country target set and proxies.
There is no sibling-project runtime or regeneration dependency.

## Validation

`tests/test_individual_handcalc.py` validates the individual lifetime YLL
formula against an explicit hand calculation (the spec's key requirement). US
sanity checks live in `tests/test_assessment.py`.
