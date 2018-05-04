
from . import Task

class TaskEnv(Task, name="env"):
    def run(self, job):
        envlist = {
            job.template(k) : job.template(v) for k,v in self.value.items()
        }

        job.create({
            'env' : envlist
        })

        job.commit(env=envlist)
