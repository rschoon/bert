
import tarfile
import tempfile

from . import Task
from ..utils import file_hash

class TaskAdd(Task, name="add"):
    def run(self, job):
        container = job.create({
            'value' : self.value,
            'file_sha256' : file_hash('sha256', self.value)
        })

        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                tar.add(self.value)
            tf.seek(0)

            container.put_archive(
                path=job.work_dir,
                data=tf
            )

        job.commit()
