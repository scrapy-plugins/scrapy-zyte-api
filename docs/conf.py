import sys
from pathlib import Path

project = "scrapy-zyte-api"
project_copyright = "2023, Zyte Group Ltd"
author = "Zyte Group Ltd"
release = "0.33.0"

sys.path.insert(0, str(Path(__file__).parent.absolute()))  # _ext
extensions = [
    "_ext",
    "enum_tools.autoenum",
    "sphinx_scrapy",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"

scrapy_intersphinx_enable = [
    "python-zyte-api",
    "scrapy-poet",
    "tenacity",
    "w3lib",
    "web-poet",
    "zyte-common-items",
    "zyte-spider-templates",
    "zyte",
]
