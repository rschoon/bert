
from . import Task

class TaskSetVar(Task, name="set-var"):
    """
    Set a variable, specified as a mapping of key/value pairs.
    """

    def run(self, job):
        for k, v in self.value.items():
            ek = job.template(k)
            ev = job.template(v)

            job.set_var(ek, ev)
