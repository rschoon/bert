
Build File Reference
====================

Build files are written using yaml syntax.

Basic YAML Primer
-----------------

YAML has a passing similarity to other data formats such as json, being composed
of several main types.

A dictionary or hash table is composed of multiple key/value pairs, and is indicated
by presense of the colon character ``:`` which seperates the key and value::

    key1: value1
    key2: value2

A list is composed by multiple values, and is indicated by presense of the the dash character
``-`` before each value::

    - value1
    - value2

In our dictionary and list examples, we provided string values.  YAML can make this a bit tricky
as these values will be used as a string, unless it is value as another type, such as a number or
boolean value.  To make sure a value is actually used as a string, you can surround it with
quotes instead.

As an extension, most strings are handled using jinja2's templating, using variables
which can be set using certain directives (such as the ``set-var`` task).

Tasks
-----

The most fundemental structure in the build file is the task list, which is indicated
by use of the `tasks` key defined as part of a stage, or at the top level of a build file::

    - tasks:
        - run: make
        - name: run tests here
          run: make check
        - name: Put what we got in a tar
          export-tar:
            paths:
              - /var/tmp/result
            dest: dist/result.tar.gz

Two different task types are used here, with `run` being used twice, and `export-tar` being
used last.  As you can see, each task is defined as a dictionary with multiple key/values.
The first key provided (aside from the name key), must be the task type, and any task configuration
is provided as the value to the task type name.  In the example, the task values are ``make``
or ``make check`` for run task, and the dictionary with the ``paths`` and ``dest`` keys for
the export-tar task.

The result for each task will produce a new container image which will be used as the image
for the next task.

Stages
------

Stages allow a build to define multiple groups of tasks.  If tasks are defined at the top level
of a build file, then the entire file is considered to be a stage.  Otherwise, stages are indicated
as a list of dictionaries in the stages key, provided at the top level::

    stages:
        build:
            tasks:
                [...]

        test:
            tasks:
                [...]

Aside from the tasks list, the image which the first task in the task list is provided as part
of the stage definition (unless it is provided as a build config)::

    stages:
        build:
            from: debian:latest
            tasks:
                [...]

Configs
-------

Sometimes you may want to provide different types of builds where each stage is run with different
parameters such as source image or variables.

Configs are provided at top level::

    configs:
        debian-stable:
            from: debian:stable
        ubuntu-lts:
            from: ubuntu:18.04
        centos-7:
            from: centos:7

    stages:
        build:
            tasks:
                [...]

