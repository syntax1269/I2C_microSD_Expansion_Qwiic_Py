# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
#
# SPDX-License-Identifier: MIT

"""Sphinx configuration for the Qwiic Python I2C microSD Expansion library."""

import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(".."))

extensions = [
    "sphinx.ext.autodoc",
    "sphinxcontrib.jquery",
    "sphinx.ext.viewcode",
]

source_suffix = {".rst": "restructuredtext"}
master_doc = "index"

project = "Qwiic Python I2C microSD Expansion Library"
author = "I2C microSD Expansion contributors"
creation_year = "2026"
current_year = str(datetime.datetime.now().year)
year_duration = (
    current_year if current_year == creation_year else creation_year + " - " + current_year
)
copyright = year_duration + " I2C microSD Expansion contributors"

version = "1.0.3"
release = "1.0.3"

language = "en"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", ".env", "DESCRIPTION.rst"]
autodoc_mock_imports = ["qwiic_i2c", "board", "busio", "micropython"]

html_theme = "sphinx_rtd_theme"
htmlhelp_basename = "QwiicI2CmicroSDExpansiondoc"

latex_documents = [
    (
        master_doc,
        "QwiicI2CmicroSDExpansion.tex",
        "Qwiic Python I2C microSD Expansion Library Documentation",
        author,
        "manual",
    )
]

man_pages = [
    (
        master_doc,
        "qwiici2cmicrosdexpansion",
        "Qwiic Python I2C microSD Expansion Library Documentation",
        [author],
        1,
    )
]

texinfo_documents = [
    (
        master_doc,
        "QwiicI2CmicroSDExpansion",
        "Qwiic Python I2C microSD Expansion Library Documentation",
        author,
        "QwiicI2CmicroSDExpansion",
        "Qwiic Python driver for the I2C microSD Expansion module.",
        "Miscellaneous",
    )
]
