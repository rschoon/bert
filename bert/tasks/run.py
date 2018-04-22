
from . import Task

class TaskRun(Task, name="run"):
    def run(self, job):
        job.create({
            'value' : self.value
        }, command=self.value)

        job.commit()

class TaskLocalRun(Task, name="local-run"):
    def run(self, job):
        subprocess.check_call(self.value, shell=True)
