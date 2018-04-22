
import os
import tarfile

from . import Task
from ..utils import file_hash

class TaskImportTar(Task, name="import-tar"):
    def run(self, job):
        if isinstance(self.value, str):
            value = {'src' : value}
        else:
            value = self.value

        dest = job.template(self.value.get('dest', job.work_dir))
        try:
            path = job.template(self.value['src'])
        except KeyError:
            path = job.template(self.value['path'])

        container = job.create({
            'file_sha256' : file_hash('sha256', path),
            'dest' : dest
        })

        with open(path, "rb") as f:
            container.put_archive(
                path=dest,
                data=f
            )

        job.commit()
