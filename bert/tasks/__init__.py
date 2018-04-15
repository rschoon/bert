
import keyword as _keyword

TASKS = {}

def get_task(name, value):
    cls = _find_task_cls(name)
    return cls(value)

def _find_task_cls(name):
    try:
        return TASKS[name]
    except KeyError:
        pass

    mod_name = _make_mod_name(__name__, name)
    try:
        __import__(mod_name)
    except ImportError:
        return None

    try:
        return TASKS[name]
    except KeyError:
        return None

def _make_mod_name(basename, name):
    name = name.replace("-", "_")
    while _keyword.iskeyword(name):
        name = name + "_"
    return "{}.{}".format(basename, name)

#
#
#

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
