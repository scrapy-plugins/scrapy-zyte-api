import os

import setuptools


def get_version():
    about = {}
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, "scrapy_zyte_api/__version__.py")) as f:
        exec(f.read(), about)
    return about["__version__"]


setuptools.setup(
    name="scrapy-zyte-api",
    version=get_version(),
    description="Client library to process URLs through Zyte API",
    long_description=open("README.rst").read(),
    long_description_content_type="text/x-rst",
    author="Zyte Group Ltd",
    author_email="info@zyte.com",
    url="https://github.com/scrapy-plugins/scrapy-zyte-api",
    packages=["scrapy_zyte_api"],
    # Sync with [pinned] @ tox.ini
    install_requires=[
        "packaging>=20.0",
        "scrapy>=2.0.1",
        "zyte-api>=0.5.1",
    ],
    extras_require={
        # Sync with [testenv:pinned-provider] @ tox.ini
        "provider": [
            "andi>=0.6.0",
            "scrapy-poet>=0.22.3",
            "web-poet>=0.17.0",
            "zyte-common-items>=0.24.0",
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)
