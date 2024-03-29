########
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.
from setuptools import setup, find_packages

from version_helpers import version


setup_kwargs = dict(
    name="solen",
    author="dusking",
    version=version(),
    license="LICENSE",
    platforms="All",
    description="Solana Token Util (Solen)",
    package_dir={"": "src"},
    packages=find_packages("src"),
    include_package_data=True,
    entry_points={
        "console_scripts": ["solen = solen_cli.main:main"],
    },
    install_requires=[
        "colorama>=0.4.4",
        "argh>=0.26.2",
        "prettytable>=0.7.2",
        "solana>=0.19.0",
        "asyncit>=0.0.4"
    ],
    python_requires=">=3.7",
)

setup(**setup_kwargs)
