<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Installation

`mealhealth` is not on PyPI; it installs from its Git repository. It needs
**Python ≥ 3.10**, and the only runtime dependencies are `numpy` and `pandas`.
The data it needs is bundled with the package, so there is nothing else to
download to use it. (Regenerating that bundled data is a separate, developer-only
task; see [Data sources](data_sources.md).)

The commands below use [uv](https://docs.astral.sh/uv/) and
[pixi](https://pixi.sh/), but plain `pip` works too. Use whatever your project
already uses.

## Add it to a project

### With uv

```bash
uv add "mealhealth @ git+https://github.com/Sustainable-Solutions-Lab/mealhealth.git"
```

### With pixi

```bash
pixi add --pypi "mealhealth @ git+https://github.com/Sustainable-Solutions-Lab/mealhealth.git"
```

### In `pyproject.toml` directly

Add the Git URL as a dependency of your own project:

```toml
[project]
dependencies = [
    "mealhealth @ git+https://github.com/Sustainable-Solutions-Lab/mealhealth.git",
]
```

Pin to a tag or commit for reproducible work by appending `@<ref>`:

```toml
dependencies = [
    "mealhealth @ git+https://github.com/Sustainable-Solutions-Lab/mealhealth.git@v0.1.0",
]
```

To keep the dependency name plain and record the source separately, uv also
reads a [`[tool.uv.sources]`](https://docs.astral.sh/uv/concepts/projects/dependencies/#git)
entry:

```toml
[project]
dependencies = ["mealhealth"]

[tool.uv.sources]
mealhealth = { git = "https://github.com/Sustainable-Solutions-Lab/mealhealth.git", tag = "v0.1.0" }
```

### With pip

```bash
pip install "git+https://github.com/Sustainable-Solutions-Lab/mealhealth.git"
```

### SSH instead of HTTPS

If you have SSH access to the repository, swap the URL scheme in any of the
commands above:

```
git+ssh://git@github.com/Sustainable-Solutions-Lab/mealhealth.git
```

## Verify

```bash
uv run python -c "import mealhealth as mh; print(len(mh.list_countries()), 'countries')"
```

(or `python -c ...` in whatever environment you installed into). This prints the
number of countries with complete bundled data.

## Develop mealhealth locally

To work *on* the package, clone it and let uv handle the environment. The first
`uv run` sets up the interpreter and installs the project together with its
`dev` dependency group:

```bash
git clone git@github.com:Sustainable-Solutions-Lab/mealhealth.git
cd mealhealth

uv run pytest -q                                   # run the test suite
uv run ruff format . && uv run ruff check .        # format + lint
uv run reuse lint                                  # license/SPDX check
```

`uv sync` up front is optional; it materialises the environment (and writes
`uv.lock`) so later `uv run` calls start instantly.

### Build these docs

This site is built with Sphinx; its dependencies are the `docs` dependency
group:

```bash
uv run --group docs sphinx-build -b html docs docs/_build/html
```

Open `docs/_build/html/index.html` in a browser. To preview with live reload
while editing, add `sphinx-autobuild` to the group and run
`uv run --group docs sphinx-autobuild docs docs/_build/html`.

:::{note}
`dev` and `docs` are [PEP 735](https://peps.python.org/pep-0735/) dependency
groups rather than installable extras, so the tooling stays out of the published
package. uv reads them directly; pip ≥ 25.1 needs `--group`. A plain
`pip install -e .` still gives a runtime-only editable install.
:::
