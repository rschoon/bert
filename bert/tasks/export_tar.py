
import os
import re
import tarfile

from . import Task, TaskVar
from ..utils import IOFromIterable, expect_file_mode, open_output

RE_TAR_EXT = re.compile(r'\.tar\.(bz2|xz|gz)$')

class TaskExportTar(Task, name="export-tar"):
    """
    Export files to a tar archive file.
    """

    class Schema:
        dest = TaskVar()
        preamble = TaskVar()
        preamble_encoding = TaskVar(default="utf-8")
        compress_type = TaskVar()
        mode = TaskVar(type=expect_file_mode)
        paths = TaskVar()

    def run_with_values(self, job, *, dest, preamble, preamble_encoding, compress_type, mode, paths):
        if os.path.exists(dest) and not job.changes:
            return

        if compress_type is None:
            m = RE_TAR_EXT.match(dest)
            if m:
                compress_type = m.group(1)
        if not compress_type:
            compress_type = ""

        with open_output(dest, "wb") as f:
            if preamble:
                if isinstance(preamble, bytes):
                    f.write(preamble)
                else:
                    f.write(preamble.encode(preamble_encoding))

            container = job.create({})
            with tarfile.open(fileobj=f, mode="w|"+compress_type) as tout:
                for path in paths:
                    self._copy_tar(container, path, tout)

            if mode is not None:
                os.fchmod(f.fileno(), mode)

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
