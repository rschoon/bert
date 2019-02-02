
from . import Task

class TaskEnv(Task, name="set-image-attr"):
    """
    Set image attributes.
    """

    def run(self, job):
        job_args = {}
        commit_args = {}
        for k,v in self.value.items():
            k,v = job.template(k), job.template(v) 

            job_args[k] = v
            if k == "env":
                commit_args["env"] = v
            elif k == "work-dir":
                commit_args["work_dir"] = v
                job.work_dir = v
            else:
                raise RuntimeError("Don't understand %r yet"%k)

        job.create(job_args)
        job.commit(**commit_args)
