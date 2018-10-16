
import subprocess

from . import Task

class TaskRun(Task, name="run"):
    def run(self, job):
        cmd = job.template(self.value)

        job.create({
            'value' : cmd
        }, command=cmd)

        job.commit()

class TaskLocalRun(Task, name="local-run"):
    def run(self, job):
        subprocess.check_call(self.value, shell=True)
