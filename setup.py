import os
import setuptools
from subspace.version import get_version

readme = open('README.md').read()

long_description = """
subspace %s

A pragmatic interface to programmatically use Ansible.

To install use:
pip install subspace
pip install git+git://git@github.com:iPlantCollaborativeOpenSource/subspace.git

----

%s

----

For more information, please see: https://github.com/iPlantCollaborativeOpenSource/subspace
""" % (get_version('short'), readme)

with open('requirements.txt') as r:
    required = r.readlines()

setuptools.setup(
    name='subspace',
    version=get_version('short'),
    author='iPlant Collaborative',
    author_email='atmodevs@gmail.com',
    description="A pragmatic interface to programmatically use Ansible.",
    long_description=long_description,
    license="Apache License, Version 2.0",
    url="https://github.com/iPlantCollaborativeOpenSource/subspace",
    packages=setuptools.find_packages(),
    install_requires=required,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries",
        "Topic :: System",
        "Topic :: System :: Clustering",
        "Topic :: System :: Distributed Computing",
        "Topic :: System :: Systems Administration"
    ])
