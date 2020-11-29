from setuptools import setup

setup(
    name='locast4plex',
    version='0.1.0',
    py_modules=['locast4plex'],
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
