
import yaml

from . import Task
from ..utils import LocalPath

class TaskIncludeVars(Task, name="include-vars"):
    """
    Read variables from another yaml file.
    """

    def run(self, job):
        with open(LocalPath(self.value, job=job)) as f:
            values = yaml.safe_load(f)
        for k, v in values.items():
            job.set_var(k, v)
