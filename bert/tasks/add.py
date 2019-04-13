
import os
import tarfile
import tempfile

from . import Task, TaskVar
from ..utils import file_hash

class TaskAdd(Task, name="add"):
    """
    Add a file or directory.
    """

    class Schema:
        path = TaskVar(bare=True)

    def run_with_values(self, job, path):
        container = job.create({
            'value' : path,
            'file_sha256' : file_hash('sha256', path)
        })

        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                tar.add(path, arcname=os.path.basename(path))
            tf.seek(0)

            container.put_archive(
                path=job.work_dir,
                data=tf
            )

        job.commit()
