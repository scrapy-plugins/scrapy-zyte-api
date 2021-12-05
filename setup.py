import setuptools

from scrapy_zyte_api import __version__


with open("README.md", "r") as fh:
    long_description = fh.read()


setuptools.setup(
    name="scrapy-zyte-api",
    version=__version__,
    packages=["scrapy_zyte_api"],
    install_requires=[
        "scrapy>=2.0,!=2.4.0",
        "aiohttp>=3.8.1",
    ],
)
