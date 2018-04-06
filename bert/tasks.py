
import os
import posixpath

TASKS = {}

def get_task(name, value):
    cls = TASKS[name]
    return cls(value)

#
#
#

class Task(object):
    def __init_subclass__(cls, name, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.name = name
        TASKS[name] = cls

    def __init__(self, value):
        self.value = value
        self.setup()

    def setup(self):
        pass

    def render_dockerfile(self, dockerfile):
        raise NotImplementedError

#
#
#

class TaskAdd(Task, name="add"):
    def render_dockerfile(self, dockerfile):
        spath = posixpath.join(dockerfile.work_dir, self.value)
        path = posixpath.join(posixpath.dirname(spath), "")
        dockerfile.append("ADD {} {}".format(self.value, path))
        dockerfile.add_file(self.value)

class TaskRun(Task, name="run"):
    def render_dockerfile(self, dockerfile):
        if self.value.startswith("./"):
            run_path = posixpath.join(dockerfile.work_dir, self.value)
            dst_path = os.path.join(os.path.dirname(run_path), "")

            dockerfile.append("ADD {} {}".format(self.value, dst_path))
            dockerfile.append("RUN {}".format(run_path))

            dockerfile.add_file(self.value)
        else:
            dockerfile.append("RUN {}".format(self.value))
