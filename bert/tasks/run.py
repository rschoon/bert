
import subprocess

from . import Task

class TaskRun(Task, name="run"):
    """
    Run a command in the container image.
    """

    def run(self, job):
        cmd = job.template(self.value)

        job.create({
            'value' : cmd
        }, command=cmd)

        job.commit()

class TaskLocalRun(Task, name="local-run"):
    """
    Run a command locally.
    """

    def run(self, job):
        subprocess.check_call(self.value, shell=True)
