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
    "myst_parser",  # Markdown source (the docs are all .md)
    "sphinx.ext.autodoc",  # pull the API reference from docstrings
    "sphinx.ext.napoleon",  # understand the NumPy-style docstrings
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",  # link out to numpy/pandas/python docs
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
    "smartquotes",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3  # auto-anchor headings so cross-page links resolve

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

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
