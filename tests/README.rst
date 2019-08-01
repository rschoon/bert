
Unit Tests
==========

There are two types of tests available.  These are the unit tests,
which test both internal APIs and external APIs in a limited and
targetted fashion.  The other tests are the functional tests
which are found in ../functests/ relative to this directory.

These tests are intended to have no external side effects, and
do not create any docker images.  Mocking can and should be
used for these tests.
