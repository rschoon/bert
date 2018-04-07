
import os
import re
from setuptools import setup, find_packages

assert sys.version_info >= (3,6)

def read(filename):
    with open(os.path.join(os.path.dirname(__file__), filename)) as f:
        return f.read()

def read_version(filename):
    force_version = os.environ.get("BERT_FORCE_BUILD_VERSION")
    if force_version:
        return force_version
    return re.search(r"__version__ = ('|\")(.*?)('|\")", read(filename)).group(2)

setup(
    name = 'bert',
    version = read_version('bert/__init__.py'),
    description = "Build things",
    author = 'Robin Schoonover',
    author_email = 'robin@cornhooves.org',
    packages = find_packages('.'),
    install_requires = [
        'click>=5.0',
        'pyyaml',
        'docker',
        'dockerpty',
    ],
    entry_points = {
        'console_scripts' : [
            "bert=bert:cli",
        ]
    }
)

