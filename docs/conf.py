# Configuration file for the Sphinx documentation builder.
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import pint_cf

project = "pint-cf"
copyright = "2026, Pedro Gámez"
author = "Pedro Gámez"
release = pint_cf.__version__
version = pint_cf.__version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "arch"]

# -- Napoleon (NumPy/Google docstrings) -------------------------------------
napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_use_rtype = False

# -- Autodoc -----------------------------------------------------------------
autodoc_member_order = "bysource"
autodoc_typehints = "description"

# -- Intersphinx --------------------------------------------------------------
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pint": ("https://pint.readthedocs.io/en/stable/", None),
}

# -- MyST ----------------------------------------------------------------------
myst_enable_extensions = ["colon_fence"]
myst_heading_anchors = 3

# -- HTML output ---------------------------------------------------------------
html_theme = "furo"
