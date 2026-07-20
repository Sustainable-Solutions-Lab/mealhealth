<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Development

This page covers working *on* mealhealth. To use it as a dependency, see
[Installation](../guide/installation.md) instead.

## Setting up

The project uses [uv](https://docs.astral.sh/uv/). The first `uv run` creates
the environment and installs the project together with its `dev` dependency
group, so there is no separate setup step:

```bash
git clone git@github.com:Sustainable-Solutions-Lab/mealhealth.git
cd mealhealth
uv run pytest -q
```

`uv sync` up front is optional; it materialises the environment (and writes
`uv.lock`) so later `uv run` calls start instantly.

## Checks

```bash
uv run pytest -q                                   # test suite
uv run mypy                                        # strict typing, package + tools
uv run ruff format . && uv run ruff check .        # format + lint
uv run reuse lint                                  # SPDX/licence compliance
```

All four run in CI and all four must pass. mypy runs in strict mode over both
`src/mealhealth` and `tools`, which means new builder code needs real
annotations, not `Any`.

To reproduce CI's test environment exactly — a smaller install without lint,
typing or docs tooling:

```bash
uv run --locked --no-dev --group test pytest -q
```

The suite reads the processed CSVs bundled with the package and creates any
source-like fixtures it needs in temporary directories. The git-ignored
`data/raw/` inputs are **not** required to run the tests, which is deliberate:
a contributor without an IHME account can still work on the whole package.

## Dependency groups

`dev`, `test`, `data` and `docs` are
[PEP 735](https://peps.python.org/pep-0735/) dependency groups rather than
installable extras, so none of the tooling reaches the published package. uv
reads them directly; pip ≥ 25.1 needs `--group`. A plain `pip install -e .`
still gives a runtime-only editable install. Runtime dependencies are only
`numpy` and `pandas`, and that is worth preserving.

## Repository layout

```
src/mealhealth/
  foodgroups.py   # risk-factor groups, causes, age buckets, mass basis
  data.py         # cached loaders for the bundled CSVs
  model.py        # calculation engine (curves, burden, substitution, modes)
  sodium.py       # sodium mean-shift mediator model
  api.py          # public assess_meal() and helpers
  data/*.csv      # bundled processed data (+ DATA_PROVENANCE.md)
tools/            # data-build stages; see Rebuilding the bundled data
tests/            # pytest suite
docs/             # this site
```

## Building the docs

```bash
uv run --group docs sphinx-build -b html docs docs/_build/html
```

Open `docs/_build/html/index.html`. CI builds with `-W`, so **any Sphinx
warning is a build failure** — a broken cross-reference or an orphaned page will
fail the pipeline even though it renders locally. Build the site before pushing
documentation changes.

To preview with live reload, add `sphinx-autobuild` to the `docs` group and run
`uv run --group docs sphinx-autobuild docs docs/_build/html`.

The site deploys to GitHub Pages from `.github/workflows/docs.yml` on pushes to
`master`.

## Tests worth knowing about

`tests/test_individual_handcalc.py` validates the individual lifetime YLL
formula against an explicit hand calculation. It is the closest thing the
project has to a specification of the core arithmetic, so if you change the
lifetime formula, change it there first and make the engine follow.

US-focused sanity checks live in `tests/test_assessment.py` — sign, direction
and magnitude for meals whose effect is not in doubt.

```{toctree}
:hidden:

data_build
design/index
```
