
from . import Task

class TaskRun(Task, name="run"):
    def run(self, job):
        job.create({
            'value' : self.value
        }, command=self.value)

        job.commit()
