
import subprocess

from . import Task, TaskVar

class TaskRun(Task, name="run"):
    """
    Run a command in the container image.
    """

    class Schema:
        command = TaskVar(bare=True, help="Command to run")

    def run_with_values(self, job, *, command):
        job.create({
            'value': command
        }, command=command)

        job.commit()

class TaskLocalRun(Task, name="local-run"):
    """
    Run a command locally.
    """

    class Schema:
        command = TaskVar(bare=True, help="Command to run")

    def run_with_values(self, job, *, command):
        subprocess.check_call(command, shell=True)
