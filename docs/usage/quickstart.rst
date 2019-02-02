
Getting Started
===============

Bert uses a single yaml file to pull configuration from, which may reference
other files.  A minimally useful file will include a number of tasks and a
source image, as follows:

.. code-block:: yaml

    from: debian:stable

    tasks:
     - script:
         contents: |
           #!/bin/sh
           echo hello, world > /notice
     - export-tar:
         dest: example.tar.gz
         paths:
           - /notice

Bert can be provided a yaml file or it will default to `bert-build.yml`.  By
running bert on the file provided above, a single tar file named
example.tar.gz will be created.
