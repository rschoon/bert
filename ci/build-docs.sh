#!/bin/sh

set -e

mkdir -p dist

(cd docs;
    ./make-tasks.py;
    sphinx-build -b html . _build/bert-docs
)
tar -cjf dist/bert-docs.tar.bz2 -C docs/_build bert-docs
