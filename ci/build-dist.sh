#!/bin/sh

if [ ! -z "$CI" ]; then
    if [ -z "$CI_COMMIT_TAG" ]; then
         export BERT_FORCE_DIST_VERSION="{version}-dev"
    fi
fi

python setup.py sdist bdist_wheel
