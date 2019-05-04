
import os
import posixpath
import tarfile
import tempfile

from . import Task, TaskVar
from ..utils import file_hash, expect_file_mode

class TaskAdd(Task, name="add"):
    """
    Add a file or directory.
    """

    class Schema:
        path = TaskVar('src', bare=True, help="Path to local file to add")
        dest = TaskVar('dest', help="Destination path of file")
        mode = TaskVar(type=expect_file_mode, help="The unix file mode to use for the tar file.")

    def run_with_values(self, job, path, dest, mode):
        job_args = {
            'value' : path,
            'file_sha256' : file_hash('sha256', path)
        }
        if mode is not None:
            job_args['mode'] = mode

        container = job.create(job_args)

        arcname = os.path.basename(path)
        if dest is None:
            arcname = posixpath.join(job.work_dir, arcname)
        else:
            if dest.endswith("/"):
                arcname = posixpath.join(dest, arcname)
            else:
                arcname = dest

        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
               ti = tar.gettarinfo(path, arcname)

               if mode is not None:
                   ti.mode = (ti.mode & ~0o777) | mode

               if ti.isreg():
                   with open(path, "rb") as fi:
                       tar.addfile(ti, fi)
               elif tarinfo.isdir():
                   tar.addfile(ti)
                   for fn in sorted(os.listdir(path)):
                       tar.add(os.path.join(name, fn), posixpath.join(arcname, fn))
               else:
                   tar.addfile(ti)

            tf.seek(0)

            container.put_archive(
                path="/",
                data=tf
            )

        job.commit()
