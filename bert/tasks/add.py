
import os
import tarfile
import tempfile

from . import Task
from ..utils import file_hash

class TaskAdd(Task, name="add"):
    def run(self, job):
        path = job.template(self.value)

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
