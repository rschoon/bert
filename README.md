
bert
====

Bert builds things in a similar manner to the `docker build` command, but with
the intended output being things other than just docker images.

Known Limitations
------------------

* Bert does not clean up very well after itself.
* Types of tasks is currently somewhat limited (and does not have feature
  parity with `docker build`).
* The docker commit process while creating an image can timeout, but resuming
  the run after the commit actually commits will work.
* Bert doesn't integrate very well into CI servers yet.
* Needs tests and examples.

Installing
----------

From checkout, use pip: `pip install --user .`

Bert may appear on pypi in the future.

Usage
-----

`bert` or `bert bert-build.yml`
