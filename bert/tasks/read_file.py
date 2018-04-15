
import tarfile
import tempfile

from . import Task

class TaskReadFile(Task, name="read-file"):
    def run(self, job):
        container = job.create({})

        with tempfile.TemporaryFile() as tf:
            tstream, tstat = container.get_archive(self.value['path'])
            for chunk in tstream:
                tf.write(chunk)
            tf.seek(0)

            with tarfile.open(fileobj=tf, mode="r") as tar:
                for item in tar.members:
                    data = tar.extractfile(item).read().decode('utf-8')
                    if data.endswith("\n"):
                        data = data[:-1]
                    job.vars[self.value['var']] = data
                    break

        job.cancel()
