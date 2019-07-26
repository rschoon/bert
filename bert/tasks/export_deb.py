
import io
import os
import tarfile

from . import Task, TaskVar
from ..utils import TarGlobList, open_output, LocalPath

class TaskExportDeb(Task, name="export-deb"):
    """
    Export files to a debian package.


    """

    CONTROL_FIELD_ORDER_START = (
        'Package', 'Version', 'Architecture', 'Section'
    )
    CONTROL_FIELD_ORDER_END = (
        'Homepage', 'Description'
    )

    class Schema:
        dest = TaskVar("name", help="Local destination filename for package", type=LocalPath)
        paths = TaskVar(help="List of paths to include in package", type=TarGlobList)
        compress_type = TaskVar(default="xz", help="Compression to use for package")
        control = TaskVar(help="Control values for package, which is essentially the package metadata. "
                          "The control contents can be specified as the literal file contents, or as a mapping. "
                          "Consult the `Control Fields section of the Debian Policy Manual <https://www.debian.org/doc/debian-policy/ch-controlfields.html>`_ "
                          "for more information.")

    def run_with_values(self, job, *, dest, paths, compress_type, control):
        # Instead of using dpkg-deb, we'll build it manually.  This
        # allows us to avoid playing games with fakeroot, and copy
        # directly to the data tar.

        if os.path.exists(dest) and not job.changes:
            return

        if not paths:
            raise ValueError("Need a path")

        container = job.create({})
        with open_output(dest, "w+b") as far:
            far.write(b"!<arch>\n")

            # package header
            deb_bin_text = b"2.0\n"
            self._write_ar_header(far, "debian-binary", size=len(deb_bin_text))
            far.write(deb_bin_text)
            self._align_ar_data(far)

            # create control
            offset_sz_control = self._write_ar_header(far, "control.tar.gz")
            control_start = far.tell()
            with tarfile.open(fileobj=far, mode="w|gz") as tarf:
                self._write_control(job, tarf, control)
            self._update_ar_size(far, offset_sz_control, far.tell() - control_start)
            self._align_ar_data(far)

            # create data
            offset_sz_data = self._write_ar_header(far, "data.tar."+compress_type)
            data_start = far.tell()
            with tarfile.open(fileobj=far, mode="w|"+compress_type) as tarf:
                self._copy_data(container, tarf, paths)
            self._update_ar_size(far, offset_sz_data, far.tell() - data_start)
            self._align_ar_data(far)

    def _update_ar_size(self, fileobj, write_offset, new_size):
        here = fileobj.tell()
        fileobj.seek(write_offset)
        fileobj.write(self._ar_pad(new_size, 10))
        fileobj.seek(here)

    def _write_ar_header(self, fileobj, name, mode=0o100644, sz=0, ts=0, user=0, group=0, size=0):
        fileobj.write(self._ar_pad(name, 16))
        fileobj.write(self._ar_pad(ts, 12))
        fileobj.write(self._ar_pad(user, 6))
        fileobj.write(self._ar_pad(group, 6))
        fileobj.write(self._ar_pad("{:o}".format(mode), 8))
        here = fileobj.tell()
        fileobj.write(self._ar_pad(size, 10))
        fileobj.write(b"`\n")
        return here

    def _align_ar_data(self, fileobj, align=2):
        off = fileobj.tell()
        need = align - (off % align)
        if need < align:
            fileobj.write(b'\0' * need)

    def _ar_pad(self, txt, sz):
        if not isinstance(txt, bytes):
            txt = str(txt).encode('utf-8')
        if len(txt) > sz:
            return txt[:sz]
        else:
            return txt + b" "*(sz-len(txt))

    def _control_sort_key(self, key):
        try:
            idx = self.CONTROL_FIELD_ORDER_START.index(key)
        except ValueError:
            pass
        else:
            return (0, idx, key)

        try:
            idx = self.CONTROL_FIELD_ORDER_END.index(key)
        except ValueError:
            pass
        else:
            return (2, idx, key)

        return (1, key)

    def _write_control(self, job, tarf, control_data):
        if 'Package' not in control_data:
            raise RuntimeError('Missing control package name')
        if 'Version' not in control_data:
            raise RuntimeError('Missing control version')
        if 'Architecture' not in control_data:
            raise RuntimeError('Missing control architecture')

        fields = sorted(control_data.keys(), key=self._control_sort_key)
        control = io.BytesIO()
        for field in fields:
            val = control_data[field]
            if isinstance(val, list):
                val = ", ".join(map(job.template, val))
            else:
                val = job.template(val)

            control.write(field.encode('utf-8'))
            control.write(b": ")

            lines = val.split("\n")
            while lines[-1] == "":
                del lines[-1]

            if len(lines) > 1:
                for num, line in enumerate(lines):
                    if num != 0:
                        control.write(b" ")
                    if line.strip():
                        control.write(line.encode('utf-8'))
                    else:
                        control.write(b".")
                    control.write(b"\n")
            else:
                control.write(lines[0].encode('utf-8'))
                control.write(b"\n")
        control.seek(0)

        info = tarfile.TarInfo("control")
        info.size = len(control.getvalue())
        tarf.addfile(info, control)

    def _copy_data(self, container, tarf, paths):
        for ti, tdata in paths.iter_container_files(container):
            tarf.addfile(ti, tdata)
