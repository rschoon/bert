
import tarfile
import tempfile

from . import Task, TaskVar

class TaskReadFile(Task, name="read-file"):
    """
    Read contents of a file in the image into a variable.
    """

    class Schema:
        path = TaskVar(help="Container file path to read data from")
        var = TaskVar(help="Destination variable name to write file contents to")

    def run_with_values(self, job, *, var, path):
        container = job.create({})

        with tempfile.TemporaryFile() as tf:
            tstream, tstat = container.get_archive(path)
            for chunk in tstream:
                tf.write(chunk)
            tf.seek(0)

            with tarfile.open(fileobj=tf, mode="r") as tar:
                for item in tar.members:
                    data = tar.extractfile(item).read().decode('utf-8')
                    if data.endswith("\n"):
                        data = data[:-1]

                    job.set_var(var, data)
                    break

        job.cancel()
