<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Installation

`mealhealth` is not on PyPI; it installs from its Git repository. It needs
**Python ≥ 3.10**, and the only runtime dependencies are `numpy` and `pandas`.
The data it needs is bundled with the package, so there is nothing else to
download to use it. (Regenerating that bundled data is a separate,
developer-only task; see
[Rebuilding the bundled data](../development/data_build.md).)

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

In whatever environment you installed into:

```bash
python -c "import mealhealth as mh; print(len(mh.list_countries()), 'countries')"
```

This should print `175` — the number of countries with complete bundled data.
Under uv, prefix it with `uv run`.

## Next

[Quickstart](quickstart.md) covers the one function you need. To work *on*
mealhealth rather than with it, see [Development](../development/index.md).
