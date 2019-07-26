
import keyword as _keyword
import os as _os

from ..exc import BuildFailed, ConfigFailed

TASKS = {}

def get_task(name, value):
    cls = _find_task_cls(name)
    if cls is None:
        raise ValueError("No task called `%s'." % (name,))
    return cls(value)

_tasks_fully_loaded = False
def iter_tasks():
    global _tasks_fully_loaded
    if not _tasks_fully_loaded:
        for mn in _os.listdir(_os.path.dirname(__file__)):
            if mn.endswith(".py"):
                mn = mn[:-3]
                __import__(_make_mod_name(__name__, mn))

    for task in TASKS.values():
        yield task

def _find_task_cls(name):
    try:
        return TASKS[name]
    except KeyError:
        pass

    for mod_name in _iter_possible_task_mod_names(name):
        mod_name_full = _make_mod_name(__name__, mod_name)
        try:
            __import__(mod_name_full)
        except ImportError:
            pass

    try:
        return TASKS[name]
    except KeyError:
        return None

def _iter_possible_task_mod_names(name):
    yield name
    if name.startswith("local-"):
        yield name[6:]

def _make_mod_name(basename, name):
    name = name.replace("-", "_")
    while _keyword.iskeyword(name):
        name = name + "_"
    return "{}.{}".format(basename, name)

#
#
#

class TaskFailed(BuildFailed):
    pass

class Task(object):
    task_name = None
    Schema = None
    schema = None
    schema_doc = True

    def __init_subclass__(cls, name, **kwargs):
        if cls.Schema is not None and not isinstance(cls, TaskSchema):
            cls.schema = TaskSchema(cls.Schema)
        super().__init_subclass__(**kwargs)
        cls.task_name = name
        TASKS[name] = cls

    def __init__(self, value):
        self.value = value
        self.setup()

    def setup(self):
        pass

    def run(self, job):
        if self.Schema is not None:
            value = self.schema.task_apply_values(job, self.value)
        else:
            value = {'value': self.value}
        self.run_with_values(job, **value)

    def run_with_values(self, job, **kwargs):
        raise NotImplementedError

def _fixup_var_name(name):
    return name.replace("_", "-")

class TaskSchema(object):
    def __init__(self, schema):
        self.bare = None
        self.values = {}
        self.aliases = {}
        self.extra = None

        for k, v in schema.__dict__.items():
            if isinstance(v, TaskVar):
                self.__add_var(k, v)

    def __add_var(self, key, var):
        var.name = key
        if var.bare:
            self.bare = var
        self.values[_fixup_var_name(key)] = var
        for alias in var.aliases:
            self.aliases[alias] = var
        if var.extra:
            self.extra = var

    def task_apply_values(self, job, value):
        vals = {}
        if isinstance(value, dict):
            extras = None
            for k, v in value.items():
                k = job.template(k)
                varobj = self.values.get(k)
                if varobj is None:
                    varobj = self.aliases.get(k)
                if varobj is not None:
                    varobj.handle(vals, job, v)
                else:
                    if self.extra is None:
                        raise ConfigFailed("Unknown item `%s' found" % k, element=value)
                    else:
                        if extras is None:
                            extras = {}
                        extras[k] = v

            if extras is not None:
                self.extra.handle(vals, job, extras)
        else:
            if self.bare is None:
                raise ConfigFailed("Non-mapping provided but map is required", element=value)
            self.bare.handle(vals, job, value)

        for name, item in self.values.items():
            if item.name not in vals:
                if item.required:
                    raise ConfigFailed("Missing required %s" % name, element=value)
                vals[item.name] = item.default

        return vals

class TaskVar(object):
    name = None

    def __init__(self, *aliases, bare=False, extra=False, default=None, type=None, required=False, help=None):
        self.bare = bare
        self.aliases = aliases
        self.extra = extra
        self.default = default
        self.type = type
        self.required = required
        self.help = help

    def handle(self, vals, job, value):
        value = job.template(value)
        if self.type is not None:
            if isinstance(self.type, type) and issubclass(self.type, JobContextType):
                value = self.type(value, job)
            else:
                value = self.type(value)
        vals[self.name] = value

class JobContextType(object):
    def __init__(self, value, job):
        raise NotImplementedError
