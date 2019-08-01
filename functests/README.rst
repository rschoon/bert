
Functional Tests
================

There are two types of tests available.  These are the functional
tests, which test build file inputs and verify output images are
produced as expected.  The other tests are the unit tests which
are found in ../tests/ relative to this directory.

These tests may have external side effects, and will create
docker images.  To prevent unlikely but potential harm to
user data in docker, the tests are gated behind the "BERT_FUNCTESTS"
environment variable.

It is not desirable to use mocking, but can be used to make the
tests more reliable, such as to reduce reliance on remote resource.

The actual tests are defined as yaml files, which include the bert
build file as part of it, as well as the test/assert conditions.
