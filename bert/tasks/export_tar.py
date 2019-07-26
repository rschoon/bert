
import os
import re
import tarfile

from . import Task, TaskVar
from ..utils import TarGlobList, expect_file_mode, open_output, LocalPath

RE_COMPRESS_EXT = re.compile(r'\.(bz2|xz|gz)$')

class TaskExportTar(Task, name="export-tar"):
    """
    Export files to a tar archive file.
    """

    class Schema:
        dest = TaskVar(help="The destination filename for the tar file", type=LocalPath)
        preamble = TaskVar(help="If provided, the tar file will contain this before the "
                           "actual tar contents.  This can be used to make a self extracting "
                           "runnable.")
        preamble_encoding = TaskVar(default="utf-8",
                                    help="The encoding to write the preamble out as. "
                                    "Used if preamble is not provided as YAML !!binary type.")
        compress_type = TaskVar(help="The compression type to use for the tar file. "
                                "If not specified, the compression type will be inferred from "
                                "the destination file name.")
        mode = TaskVar(type=expect_file_mode, help="The unix file mode to use for the tar file.")
        paths = TaskVar(help="List of paths to include in tar file", type=TarGlobList)

    def run_with_values(self, job, *, dest, preamble, preamble_encoding, compress_type, mode, paths):
        if hasattr(dest, "__fspath__"):
            dest = dest.__fspath__()

        if os.path.exists(dest) and not job.changes:
            return

        if compress_type is None:
            m = RE_COMPRESS_EXT.search(dest)
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
                for ti, tdata in paths.iter_container_files(container):
                    tout.addfile(ti, tdata)

            if mode is not None:
                os.fchmod(f.fileno(), mode)
