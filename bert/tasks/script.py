
import posixpath
import tarfile
import tempfile

from . import Task
from ..utils import file_hash

class TaskScript(Task, name="script"):
    def run(self, job):
        if isinstance(self.value, list):
            script = self.value
        else:
            script = [self.value]

        script = [job.template(a) for a in script]
        script_val = script[0] if len(script) == 1 else script
        command = posixpath.join(job.work_dir, script[0])

        container = job.create({
            'value' : script_val,
            'file_sha256' : file_hash('sha256', script[0])
        }, command=[command]+script[1:])

        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                tar.add(script[0])
            tf.seek(0)

            container.put_archive(
                path=job.work_dir,
                data=tf
            )

        job.commit()
