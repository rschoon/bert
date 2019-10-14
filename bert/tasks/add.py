
import os
import posixpath
import tarfile
import tempfile

from . import Task, TaskVar
from ..utils import expect_file_mode, IOHashWriter, LocalPath

class TaskAdd(Task, name="add"):
    """
    Add a file or directory.
    """

    class Schema:
        path = TaskVar('src', bare=True, help="Path to local file to add", type=LocalPath)
        dest = TaskVar('dest', help="Destination path of file")
        mode = TaskVar(type=expect_file_mode, help="The unix file mode to use for the tar file.")
        template = TaskVar(help="Treat added file as a template", default=False, type=bool)

    def run_with_values(self, job, path, dest, mode, template):
        if hasattr(path, '__fspath__'):
            path = path.__fspath__()

        job_args = {
            'value': path,
        }
        if mode is not None:
            job_args['mode'] = mode
        if template:
            job_args['template'] = True

        arcname = os.path.basename(path)
        if dest is None:
            arcname = posixpath.join(job.work_dir, arcname)
        else:
            if dest.endswith("/"):
                arcname = posixpath.join(dest, arcname)
            else:
                arcname = dest

        with tempfile.TemporaryFile() as tf:
            hash_wrapper = IOHashWriter('sha256', tf)

            with tarfile.open(fileobj=hash_wrapper, mode="w") as tar:
                job.tarfile_add(tar, path, arcname=arcname, mode=mode, template=template)

            tf.seek(0)
            job_args['tar_sha256'] = hash_wrapper.hexdigest()

            container = job.create(job_args)
            container.put_archive(
                path="/",
                data=tf
            )

        job.commit()
