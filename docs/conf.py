# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: CC-BY-4.0

"""Sphinx configuration for the mealhealth documentation site."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

# -- Project information -----------------------------------------------------

project = "mealhealth"
author = "Koen van Greevenbroek"
copyright = "2026 Koen van Greevenbroek"  # noqa: A001

try:
    release = _pkg_version("mealhealth")
except PackageNotFoundError:  # not installed (e.g. a bare docs checkout)
    release = "0.1.0"
version = release

# -- General configuration ---------------------------------------------------

extensions = [
    "myst_nb",  # Markdown source (the docs are all .md) + executed notebooks
    "sphinx.ext.autodoc",  # pull the API reference from docstrings
    "sphinx.ext.napoleon",  # understand the NumPy-style docstrings
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",  # link out to numpy/pandas/python docs
    "sphinx.ext.mathjax",  # render mathematical notation in HTML
    "sphinx.ext.viewcode",  # "[source]" links in the API reference
    "sphinx_copybutton",  # copy button on code blocks
]

autosummary_generate = True
autodoc_member_order = "bysource"
autodoc_typehints = "description"

napoleon_google_docstring = False
napoleon_numpy_docstring = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
}

# -- MyST (Markdown) ---------------------------------------------------------

myst_enable_extensions = [
    "colon_fence",  # ::: fenced directives
    "deflist",
    "dollarmath",  # $inline$ and $$display$$ mathematics
    "smartquotes",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3  # auto-anchor headings so cross-page links resolve

# -- MyST-NB (executed example notebooks) ------------------------------------

# The notebooks in examples/ are MyST Markdown with no stored outputs, so they
# execute on every build. That keeps the figures honest — they are produced by
# the code shown, against the bundled data — and makes the docs build double as
# an integration test of the public API.
nb_execution_mode = "cache"
nb_execution_timeout = 300
nb_execution_raise_on_error = True  # a failing example must fail the build
nb_execution_working_dir = "examples"  # so the notebooks can import mhstyle
nb_merge_streams = True

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "examples/mhstyle.py"]

# -- HTML output -------------------------------------------------------------

html_theme = "furo"
html_title = f"mealhealth {release}"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

html_theme_options = {
    "source_repository": "https://github.com/Sustainable-Solutions-Lab/mealhealth/",
    "source_branch": "master",
    "source_directory": "docs/",
}
