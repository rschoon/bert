
import os
import re
import tarfile

from . import Task
from ..utils import IOFromIterable

RE_TAR_EXT = re.compile(r'\.tar\.(bz2|xz|gz)$')

class TaskExportTar(Task, name="export-tar"):
    def run(self, job):
        try:
            dest = job.template(self.value["dest"])
        except KeyError:
            dest = job.template(self.value["name"])

        if os.path.exists(dest) and not job.changes:
            return

        paths = self.value.get('paths', [])

        comp = self.value.get("compress-type", None)
        if comp is None:
            m = RE_TAR_EXT.match(dest)
            if m:
                comp = m.group(1)
        if not comp:
            comp = ""

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest+".tmp", "wb") as f:

            container = job.create({})
            with tarfile.open(fileobj=f, mode="w|"+comp) as tout:
                for path in paths:
                    self._copy_tar(container, path, tout)
        os.rename(dest+".tmp", dest)

    def _copy_tar(self, container, path, tout):
        tstream, tstat = container.get_archive(path)
        tf = IOFromIterable(tstream)

        with tarfile.open(fileobj=tf, mode="r|") as tin:
            while True:
                ti = tin.next()
                if ti is None:
                    break

                ti.name = os.path.join(os.path.dirname(path), ti.name)

                tdata = tin.extractfile(ti) if ti.isreg() else None
                tout.addfile(ti, tdata)
