
import os
import re
from setuptools import setup, find_packages
import sys

assert sys.version_info >= (3,6)

def read(filename):
    with open(os.path.join(os.path.dirname(__file__), filename)) as f:
        return f.read()

def read_version(filename):
    version = re.search(r"__version__ = ('|\")(.*?)('|\")", read(filename)).group(2)
    force_version = os.environ.get("BERT_FORCE_DIST_VERSION")
    if force_version:
        return force_version.format(version=version)
    return version

setup(
    name = 'bert-build',
    version = read_version('bert/__init__.py'),
    description = "Build things",
    author = 'Robin Schoonover',
    author_email = 'robin@cornhooves.org',
    url = 'https://git.cornhooves.org/build-tools/bert',
    long_description=read("README.md"),
    long_description_content_type='text/markdown',
    packages = find_packages('.'),
    install_requires = [
        'click>=5.0',
        'pyyaml',
        'docker',
        'dockerpty',
        'jinja2',
        'requests',
        'whatthepatch>=0.0.6'
    ],
    extras_require = {
        'docs':  ["Sphinx"],
    },
    entry_points = {
        'console_scripts' : [
            "bert=bert:cli",
        ]
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Topic :: Software Development :: Build Tools',
        'Environment :: Console',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
)

