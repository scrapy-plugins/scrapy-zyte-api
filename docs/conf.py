import sys
from pathlib import Path

project = "scrapy-zyte-api"
copyright = "2023, Zyte Group Ltd"
author = "Zyte Group Ltd"
release = "0.29.0"

sys.path.insert(0, str(Path(__file__).parent.absolute()))  # _ext
extensions = [
    "_ext",
    "enum_tools.autoenum",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"

intersphinx_mapping = {
    "python": (
        "https://docs.python.org/3",
        None,
    ),
    "python-zyte-api": (
        "https://python-zyte-api.readthedocs.io/en/stable",
        None,
    ),
    "scrapy": (
        "https://docs.scrapy.org/en/latest",
        None,
    ),
    "scrapy-poet": (
        "https://scrapy-poet.readthedocs.io/en/stable",
        None,
    ),
    "tenacity": (
        "https://tenacity.readthedocs.io/en/latest",
        None,
    ),
    "w3lib": (
        "https://w3lib.readthedocs.io/en/latest",
        None,
    ),
    "web-poet": (
        "https://web-poet.readthedocs.io/en/stable",
        None,
    ),
    "zyte": (
        "https://docs.zyte.com",
        None,
    ),
    "zyte-common-items": (
        "https://zyte-common-items.readthedocs.io/en/latest",
        None,
    ),
    "zyte-spider-templates": (
        "https://zyte-spider-templates.readthedocs.io/en/latest",
        None,
    ),
}
