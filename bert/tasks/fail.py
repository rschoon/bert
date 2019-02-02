
from . import Task, TaskFailed

class TaskFail(Task, name="fail"):
    """
    Force the build to fail.
    """

    def run(self, job):
        raise TaskFailed()
