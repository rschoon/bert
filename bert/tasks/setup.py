
import io
import tarfile
import tempfile

from . import Task

class TaskSetup(Task, name="setup"):
    def run(self, job):
        container = job.create({})

        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                info = tarfile.TarInfo(job.work_dir)
                info.type = tarfile.DIRTYPE
                tar.addfile(info, io.BytesIO())
            tf.seek(0)

            container.put_archive(
                path="/",
                data=tf
            )

        job.commit()
