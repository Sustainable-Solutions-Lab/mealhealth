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
tools/prepare_data.py              # regenerate health/demographic data from raw (dev only)
tools/generate_rr_age_attenuation.py # one-off: curated RR age-attenuation table from GBD 2019
tools/baseline_diet_from_glade.py  # build baseline diet (temporary; see docstring)
tools/reference/*.csv              # curated regeneration inputs (red-meat RR, TMREL, age attenuation)
tests/                  # pytest suite
docs/                   # methodology, food groups, data sources, usage
```

## Key design decisions

* **Per-country.** The model works at the country level directly — there is no
  optimisation or country clustering here.
* **GBD 2023 vintage throughout.** Relative-risk curves come from the GBD 2023
  Burden-of-Proof tool (age-aggregated; fetched without login), age-expanded via
  a curated attenuation table (GBD 2019 age shape, normalized to the 60-64
  reference age) and clipped at curated TMRELs. Mortality is GBD 2023.
* **Direct curve evaluation.** RR is read off the curve by log-linear
  interpolation.
* **Relative to baseline.** PAF is `1 − RR(x)/RR(x_base)`; the PAF carries no
  TMREL term — the TMREL only shapes where each bundled curve plateaus.
* **Processed meat is separate** from red meat (its own GBD 2023 curve; the
  baseline split comes from the GDD-IA processed fraction).
* **Mass basis** reconciles GBD's native exposure bases with measured intakes;
  the meal input basis is documented per group in `docs/food_groups.md`.

## Dev workflow

```bash
uv venv .venv && . .venv/bin/activate && uv pip install -e ".[dev]"
python -m pytest -q
ruff format . && ruff check .
reuse lint
```

## Regenerating bundled data

Health/demographic data regenerates from public raw datasets (see
`docs/data_sources.md` for what to download into `data/raw/`; the UN WPP files
and the GBD 2023 Burden-of-Proof RR curves download automatically):

```bash
python tools/prepare_data.py
```

The RR age structure and TMRELs are read from curated tables under
`tools/reference/`; `tools/generate_rr_age_attenuation.py` is a one-off that
rebuilds `rr_age_attenuation.csv` from the GBD 2019 RR workbook (the only
remaining use of GBD 2019, as the donor for the age shape).

The baseline diet (`baseline_intake.csv`, `baseline_calories.csv`) is a separate
bundled dataset; its committed CSVs are canonical and need no regeneration.
`tools/baseline_diet_from_glade.py` is a **temporary** builder sourcing it from
the **GLADE** project (the Global Land, Agriculture, Diet and Emissions model,
formerly `food-opt`) until the dataset is published on Zenodo — the only place
the project still references GLADE.

## Validation

`tests/test_individual_handcalc.py` validates the individual lifetime YLL
formula against an explicit hand calculation (the spec's key requirement). US
sanity checks live in `tests/test_assessment.py`.
