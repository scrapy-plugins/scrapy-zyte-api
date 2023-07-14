import setuptools

setuptools.setup(
    name="scrapy-zyte-api",
    version="0.10.0",
    description="Client library to process URLs through Zyte API",
    long_description=open("README.rst").read(),
    long_description_content_type="text/x-rst",
    author="Zyte Group Ltd",
    author_email="info@zyte.com",
    url="https://github.com/scrapy-plugins/scrapy-zyte-api",
    packages=["scrapy_zyte_api"],
    install_requires=[
        "packaging>=20.0",
        "scrapy>=2.0.1",
        "zyte-api>=0.4.0",
    ],
    extras_require={
        "provider": [
            "scrapy-poet>=0.10.0",
            "web-poet>=0.13.0",
            "zyte-common-items>=0.7.0",
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
