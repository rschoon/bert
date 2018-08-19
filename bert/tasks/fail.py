
from . import Task, TaskFailed

class TaskFail(Task, name="fail"):
    def run(self, job):
        raise TaskFailed()
