"""
This module contains setup configurations for installing this package
"""
from setuptools import setup, find_packages

from version_helpers import version


setup_kwargs = dict(
    name="tiny_solana",
    version=version(),
    license="LICENSE",
    platforms="All",
    description="Tiny Solana Util",
    package_dir={"": "src"},
    packages=find_packages("src"),
    include_package_data=True,
    entry_points={
        "console_scripts": ["tiny = cli_tiny.main:main"],
    },
    install_requires=[
        "solana",
        "colorama",
        "argh"
    ],
    python_requires=">=3.7",
)

setup(**setup_kwargs)
