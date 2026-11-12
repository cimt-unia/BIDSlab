#  Copyright (c) 2026 by Lukas Behammer
#  University of Augsburg
#  Department of Computer Science
#  Chair of Informatics for Medical Technology
#
#  SPDX-License-Identifier: BSD-3-Clause

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

from sphinx.ext import autodoc
from importlib.metadata import version as get_version

sys.path.insert(0, os.path.abspath("../../src"))

release = get_version("bidslab")
version = release

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "BIDSlab"
copyright = "2025, Lukas Behammer"
author = "Lukas Behammer"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.coverage",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    "sphinx.ext.mathjax",
    "sphinx.ext.autosummary",
    "numpydoc",
    "myst_parser",
    "sphinxcontrib.email",
    "sphinx_copybutton",
    "sphinx_last_updated_by_git",
    "pytest_doctestplus.sphinx.doctestplus",
]

templates_path = ["_templates"]
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]
# html_favicon = '../../branding/logo/Logo_BIDSlab_wo-text.svg'
html_title = f"{project} v{release}"
html_baseurl = os.environ.get("READTHEDOCS_CANONICAL_URL", "/")
# html_logo = "../../branding/logo.png"
html_theme_options = {
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/cimt-unia/bidslab",
            "icon": "fa-brands fa-github",
            "type": "fontawesome",
        }
    ],
    "icon_links_label": "Quick Links",
    "use_edit_page_button": True,
    "secondary_sidebar_items": [
        "page-toc",
        "edit-this-page",
        "sourcelink",
        "sidebar-ethical-ads.html"
    ],
    "show_prev_next": False,
    "footer_start": ["copyright"],
    "footer_center": ["sphinx-version"],
    "footer_end": ["theme-version"],
    # "logo": {
    #     "text": f"{project} v{release}",
    #     "image_light": "../../branding/logo.png",
    # },
}
html_context = {
    "github_user": "cimt-unia",
    "github_repo": "bidslab",
    "github_version": "main",
    "doc_path": "docs/source",
}
html_sidebars = {
    "quickstart": [],
    "developer_guide": [],
    "changelog": [],
}

# -- Options for Autosummary -------------------------------------------------
autosummary_generate = True
autosummary_imported_members = True

# -- Options for Autodoc -----------------------------------------------------

###############################################
# Source - https://stackoverflow.com/a/79492670
# Posted by jxrossel
# Retrieved 2026-01-12, License - CC BY-SA 4.0

autodoc.Documenter.member_order = 0
autodoc.DataDocumenter.member_order = 10
autodoc.FunctionDocumenter.member_order = 20
autodoc.ClassDocumenter.member_order = 30
autodoc.AttributeDocumenter.member_order = 40
autodoc.PropertyDocumenter.member_order = 40
autodoc.MethodDocumenter.member_order = 50
autodoc.ExceptionDocumenter.member_order = 60
###############################################

autodoc_member_order = "groupwise"
autodoc_default_options = {
    "members": None,
    # "member-order": "bysource",
    # "exclude-members": "__init__",
    # "inherited-members": None,
}

# -- Options for Napoleon -----------------------------------------------------
napoleon_google_docstring = False
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = True
napoleon_use_rtype = False
napoleon_preprocess_types = True
napoleon_custom_sections = [("Attributes", "params_style")]
napoleon_type_aliases = {
    "A": "bidslab.common.base.BaseAcquisition",
    "E": "bidslab.common.base.Entity",
    "EV": "bidslab.common.specs_misc.Event",
    "R": "bidslab.common.specs_misc.Run",
    "SC": "bidslab.common.specs_summary.Scan",
    "T": "bidslab.common.base.BaseTask",
}

# -- Options for Todo ---------------------------------------------------------
todo_include_todos = True
todo_link_only = True

# -- Options for Numpydoc -----------------------------------------------------
numpydoc_show_inherited_class_members = True
numpydoc_class_members_toctree = False
numpydoc_attributes_as_param_list = True

# -- Options for Coverage -----------------------------------------------------
coverage_modules = ["bidslab"]
coverage_statistics_to_stdout = True
