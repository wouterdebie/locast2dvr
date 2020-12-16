from os import path
import os

from setuptools import setup, setuptools

with open(path.join(path.abspath(path.dirname(__file__)), 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

install_requires = [
    'click~=7.1.0',
    'click-config-file~=0.6.0',
    'click-option-group~=0.5.0',
    'Flask~=1.1.0',
    'fuzzywuzzy~=0.18.0',
    'm3u8~=0.7.0',
    'requests~=2.24.0',
    'waitress~=1.4.0',
    'Paste~=3.5.0',
    'tabulate~=0.8.0'
]

if os.name != 'nt':
    install_requires.append('python-Levenshtein~=0.12.0')

setup(
    name='locast2dvr',
    version='0.4.18',
    description='locast to Plex Media Server/Emby integration',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/wouterdebie/locast2dvr",
    author="Wouter de Bie",
    author_email="pypi@evenflow.nl",
    license="MIT",
    py_modules=['locast2dvr'],
    packages=setuptools.find_packages(),
    include_package_data=True,
    python_requires='~=3.7',
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
    ],
    install_requires=install_requires,
    entry_points='''
        [console_scripts]
        locast2dvr=locast2dvr:cli
    ''',
)
