"""Sphinx configuration for FIRM Protocol documentation."""

import os
import sys

# Add source directory to sys.path for autodoc
sys.path.insert(0, os.path.abspath("../src"))

# -- Project information -------------------------------------------------------
project = "FIRM Protocol"
copyright = "2026, FIRM Protocol Contributors"
author = "FIRM Protocol Contributors"
release = "0.5.0"

# -- General configuration -----------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autosummary",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Napoleon settings (Google + NumPy docstring styles)
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True

# Autodoc settings
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"
autosummary_generate = True

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- Options for HTML output ---------------------------------------------------
html_theme = "alabaster"
html_theme_options = {
    "description": "Self-Evolving Autonomous Organization Runtime",
    "github_user": "firm-protocol",
    "github_repo": "firm",
    "github_button": True,
    "github_type": "star",
}
html_static_path = ["_static"]
