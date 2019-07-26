
import os
import shutil
import stat

from . import Task, TaskVar
from ..utils import TarGlobList, LocalPath

def _makedev(path, ti):
    mode = ti.mode | (stat.S_IFBLK if ti.isblk() else stat.S_IFCHR)
    os.mknod(path, mode, os.makedev(ti.devmajor, ti.devminor))

def _makelink(path, ti):
    os.symlink(ti.linkname, path)

def _setmeta(path, ti):
    try:
        os.chmod(path, ti.mode)
    except EnvironmentError:
        pass

    try:
        os.utime(path, (ti.mtime, ti.mtime))
    except EnvironmentError:
        pass

class TaskExportFile(Task, name="export-file"):

    class Schema:
        dest = TaskVar(help="Destination file name", type=LocalPath)
        paths = TaskVar('src', help="File or list of files to export", required=True, type=TarGlobList)

    def run_with_values(self, job, dest=None, paths=None):
        if hasattr(dest, "__fspath__"):
            dest = dest.__fspath__()

        if os.path.isfile(dest) and not job.changes:
            return

        container = job.create({})

        dest_temp = self._do_export(container, paths, dest)

        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.rename(dest_temp, dest)

    def _do_export(self, container, paths, dest):
        made_dest = force_dir = is_dir = False
        while dest.endswith("/"):
            force_dir = True
            dest = dest[:-1]

        dest_out = dest+".tmp"
        for ti, tdata in paths.iter_container_files(container):
            if not made_dest and (ti.isdir() or force_dir):
                os.makedirs(dest_out, exist_ok=True)
                made_dest = True
                is_dir = True

            tipath = ti.name
            while tipath.startswith("/"):
                tipath = tipath[1:]

            if is_dir:
                tipath = os.path.join(dest_out, tipath)
            else:
                tipath = dest_out

            try:
                self._extract_file(tipath, ti, tdata)
            finally:
                if tdata is not None:
                    tdata.close()

        return dest_out

    def _extract_file(self, path, ti, tdata):
        os.makedirs(os.path.dirname(path), exist_ok=True)

        if ti.isreg():
            with open(path, "wb") as f:
                shutil.copyfileobj(tdata, f)
        elif ti.isdir():
            os.makedirs(path, exist_ok=True)
        elif ti.isfifo():
            os.mkfifo(path)
        elif ti.ischr() or ti.isblk():
            _makedev(path, ti)
        elif ti.issym():
            _makelink(path, ti)
        else:
            return

        if not ti.issym():
            _setmeta(path, ti)
