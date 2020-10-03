from setuptools import setup

setup(
    name='locast4plex',
    version='0.1',
    py_modules=['locast4plex'],
    install_requires=[
        'Click',
    ],
    entry_points='''
        [console_scripts]
        locast4plex=locast4plex:cli
    ''',
)
