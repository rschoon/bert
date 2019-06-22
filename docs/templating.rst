
Templating
==========

To increase the flexibility in task definitions, bert uses the jinja template
engine which is applied to most values in the bert-build yaml. This allows for
variable substitution and various control structures within task and other values.

For more information, see the `jinja documentation <http://jinja.pocoo.org/docs/latest/templates/>`_.

Variables
---------

Variables can be provided via several sources, such as the ``set-var`` task
and the ``include-var`` task and config/top-level directive.  Several variables
are also provided automatically for the current config and stage.

