from os import path

from setuptools import setup, setuptools

with open(path.join(path.abspath(path.dirname(__file__)), 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='locast4plex',
    version='0.1.0',
    description='locast to Plex Media Server integration',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/wouterdebie/locast4plex",
    author="Wouter de Bie",
    author_email="pypi@evenflow.nl",
    license="MIT",
    py_modules=['locast4plex'],
    packages=setuptools.find_packages(),
    include_package_data=True,
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
    ],
    install_requires=[
        'click',
        'click>=7.1.2',
        'click-config-file>=0.6.0',
        'click-option-group>=0.5.1',
        'Flask>=1.1.2',
        'fuzzywuzzy>=0.18.0',
        'm3u8>=0.7.1',
        'requests>=2.24.0',
        'waitress>=1.4.4'
    ],
    entry_points='''
        [console_scripts]
        locast4plex=locast4plex:cli
    ''',
)
