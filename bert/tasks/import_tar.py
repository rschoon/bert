
import os
import tarfile

from . import Task, TaskVar
from ..utils import file_hash

class TaskImportTar(Task, name="import-tar"):
    """
    Import files from a tar archive file into the image.
    """

    class Schema:
        dest = TaskVar()
        src = TaskVar('path', bare=True)

    def run_with_values(self, job, *, src, dest):
        if dest is None:
            dest = job.work_dir

        container = job.create({
            'file_sha256' : file_hash('sha256', src),
            'dest' : dest
        })

        with open(src, "rb") as f:
            container.put_archive(
                path=dest,
                data=f
            )

        job.commit()
