#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='pyresceneauto',
    version='2.0',
    description='Effortlessly turn extracted scene releases back into their original glory with the aid of pyRescene and srrdb.com',
    author='jaloji',
    license='WTFPL',
    url='https://github.com/jaloji/pyautorescene',
    packages=find_packages(),
    scripts=['bin/autorescene.py'],

    keywords=['rescene', 'srr', 'srs', 'scene', 'resample', 'automate', 'auto'],
    install_requires=['requests', 'colorama'],
    # requests is used for HTTP requests to srrdb.com
    # colorama is used for pretty printing in verbose mode
)
