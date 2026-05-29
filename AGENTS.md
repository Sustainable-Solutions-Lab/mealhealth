<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Developer notes (AGENTS.md / CLAUDE.md)

## What this is

`mealhealth` is a small, installable Python package that turns a meal (in
food-group terms + calories) into a change in years of life lost, using GBD
relative-risk curves and a per-country baseline diet. It is a standalone
distillation of the diet→health calculation in the sibling `food-opt` project.

## Layout

```
src/mealhealth/
  foodgroups.py   # risk-factor groups, causes, age buckets, mass basis
  data.py         # cached loaders for bundled CSVs
  model.py        # calculation engine (curves, burden, substitution, modes)
  api.py          # public assess_meal() and helpers
  data/*.csv      # bundled processed data (+ DATA_PROVENANCE.md)
tools/prepare_data.py   # regenerate bundled data from food-opt (dev only)
tests/                  # pytest suite
docs/                   # methodology, food groups, data sources, usage
```

## Key design decisions

* **Per-country, not clustered.** Unlike `food-opt` (which clusters countries
  for its LP), `mealhealth` works at the country level directly — more accurate
  and simpler since there is no optimisation here.
* **Direct curve evaluation.** RR is read off the GBD curve by log-linear
  interpolation; none of `food-opt`'s SOS2/PWL machinery is needed.
* **Relative to baseline.** PAF is `1 − RR(x)/RR(x_base)`; no TMREL.
* **Processed meat is separate** from red meat (GBD curve + GDD-IA split),
  which `food-opt` does not do.
* **Mass basis** matches `food-opt`'s reconciled model basis; the meal input
  basis is documented per group in `docs/food_groups.md`.

## Dev workflow

```bash
uv venv .venv && . .venv/bin/activate && uv pip install -e ".[dev]"
python -m pytest -q
ruff format . && ruff check .
reuse lint
```

## Regenerating bundled data

Requires a `food-opt` checkout with its licensed raw GBD/GDD data:

```bash
cd /path/to/food-opt
.pixi/envs/default/bin/python /path/to/meal-health-indicator/tools/prepare_data.py
```

The path to `food-opt` is configured at the top of `tools/prepare_data.py`.

## Validation

`tests/test_individual_handcalc.py` validates the individual lifetime YLL
formula against an explicit hand calculation (the spec's key requirement). US
sanity checks live in `tests/test_assessment.py`.
