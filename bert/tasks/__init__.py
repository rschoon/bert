
import keyword as _keyword
import os as _os

from ..exc import BuildFailed

TASKS = {}

def get_task(name, value):
    cls = _find_task_cls(name)
    if cls is None:
        raise ValueError("No task called `%s'."%(name,))
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

    def __init_subclass__(cls, name, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.task_name = name
        TASKS[name] = cls

    def __init__(self, value):
        self.value = value
        self.setup()

    def setup(self):
        pass

    def run(self, job):
        raise NotImplementedError
