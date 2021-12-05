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
        "zyte-api>=0.1.2",
        "twisted>=21.7.0"
    ],
)
