
from . import Task, TaskVar

class TaskEnv(Task, name="env"):
    """
    Set container environment.
    """

    schema_doc = False

    class Schema:
        _env = TaskVar(extra=True)

    def run_with_values(self, job, _env):
        job.create({
            'env' : _env
        })

        job.commit(env=_env)
