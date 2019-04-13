
from . import Task, TaskVar

class TaskEnv(Task, name="set-image-attr"):
    """
    Set image attributes.
    """

    class Schema:
        env = TaskVar()
        work_dir = TaskVar()

    def run(self, job, *, env, work_dir):
        job_args = {}
        commit_args = {}

        if env is not None:
            job_args["env"] = env
            commit_args["env"] = env

        if work_dir is not None:
            job_args["work-dir"] = work_dir
            commit_args["work_dir"] = work_dir
            job.work_dir = work_dir

        job.create(job_args)
        job.commit(**commit_args)
