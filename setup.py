# -*- coding: utf-8 -*-

from setuptools import find_packages
from setuptools import setup
#from pkg_resources import get_distribution, DistributionNotFound
#from pkg_resources import get_distribution

import os

setup(
    name='collective.recipe.redmine',
    version='0.0.1',
    url='https://github.com/loechel/collective.recipe.redmine',
    license='Apache Software License v2',
    author='Alexander Loechel',
    author_email='Alexander.Loechel@lmu.de',
    description='',
    long_description=
        open('README.rst').read() + '\n' +
        open(os.path.join('docs', 'HISTORY.rst')).read(),
    keywords='redmine recipe zc ',
    packages=find_packages('src', exclude=['ez_setup']),
    package_dir={'': 'src'},
    namespace_packages=['collective', 'collective.recipe'],
    include_package_data=True,
    install_requires=[
        'setuptools',
        # -*- Extra requirements: -*-
        'Genshi',
        'zc.buildout',
        'svn',

        'ipython',
        'ipdb',

    ],
    zip_safe=False,
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities',
        'Topic :: Internet :: WWW/HTTP',
        'Intended Audience :: Developers',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
    entry_points={
        "zc.buildout": [
            "default = collective.recipe.redmine:SolrSingleRecipe",
            "mc = collective.recipe.redmine:MultiCoreRecipe",
        ]
    },
)
