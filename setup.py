'''
Setup for cluster-func package.
'''

# Always prefer setuptools over distutils
from setuptools import setup, find_packages
# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='cluster-func',

    # Versions should comply with PEP440.  For a discussion on 
	# single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version='0.0.0',

    description='Run a function many times on many processes / machines',
    long_description=long_description,

    # The project's main homepage.
    url='https://github.com/enewe101/cluster-func',

    # Author details
    author='Edward Newell',
    author_email='edward.newell@gmail.com',

    # Choose your license
    license='MIT',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 3 - Alpha',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: MIT License',

        # Specify the Python versions you support here. In particular, 
		# ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 2.7',
    ],

    keywords=(
		'threading multiprocessing schedule scheduling batch process processing '
		'queue queueing cluster qsub pbs'
	),

    packages=['cluster_func'],

	package_data={
		'cluster_func': ['README.md']
	},

	scripts = [
		'bin/cluf',
	],

	install_requires=[
		'iterable-queue',
	],

)
