#!/bin/sh

set -e

pip install tox
tox -e "$1"
