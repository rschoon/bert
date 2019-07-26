
from . import Task, TaskVar
from ..utils import file_hash, LocalPath

class TaskImportTar(Task, name="import-tar"):
    """
    Import files from a tar archive file into the image.
    """

    class Schema:
        dest = TaskVar(help="Destination path in image to unpack tar file to.")
        src = TaskVar('path', bare=True, help="Local source path of tar file", type=LocalPath)

    def run_with_values(self, job, *, src, dest):
        if dest is None:
            dest = job.work_dir

        container = job.create({
            'file_sha256': file_hash('sha256', src),
            'dest': dest
        })

        with open(src, "rb") as f:
            container.put_archive(
                path=dest,
                data=f
            )

        job.commit()
