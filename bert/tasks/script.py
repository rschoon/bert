
import posixpath
import tarfile
import tempfile

from . import Task
from ..utils import file_hash

class TaskScript(Task, name="script"):
    def run(self, job):
        command = posixpath.join(job.work_dir, self.value)

        container = job.create({
            'value' : self.value,
            'file_sha256' : file_hash('sha256', self.value)
        }, command=command)

        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                tar.add(self.value)
            tf.seek(0)

            container.put_archive(
                path=job.work_dir,
                data=tf
            )

        job.commit()
