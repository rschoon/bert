
import yaml

from . import Task

class TaskIncludeVars(Task, name="include-vars"):
    def run(self, job):
        with open(self.value) as f:
            values = yaml.safe_load(f)
        for k,v in values.items():
            job.set_var(k, v)
