
import io
import os
import tarfile

from . import Task
from ..utils import IOFromIterable

class TaskExportDeb(Task, name="export-deb"):
    CONTROL_FIELD_ORDER_START = (
        'Package', 'Version', 'Architecture', 'Section'
    )
    CONTROL_FIELD_ORDER_END = (
        'Homepage', 'Description'
    )

    def run(self, job):
        # Instead of using dpkg-deb, we'll build it manually.  This
        # allows us to avoid playing games with fakeroot, and copy
        # directly to the data tar.

        container = job.create({})

        # allow either
        paths = self.value.get('paths', [])
        install_path = self.value.get('install-path')
        if install_path:
            paths.append(paths)

        # collect other details
        name = os.path.join(job.dist_dir, job.template(self.value["name"]))
        comp = self.value.get("compress-type", "xz")

        if not paths:
            raise RuntimeError("Need a path")

        os.makedirs(job.dist_dir, exist_ok=True)
        with open(name, "w+b") as far:
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
                self._write_control(job, tarf)
            self._update_ar_size(far, offset_sz_control, far.tell() - control_start)
            self._align_ar_data(far)

            # create data
            offset_sz_data = self._write_ar_header(far, "data.tar."+comp)
            data_start = far.tell()
            with tarfile.open(fileobj=far, mode="w|"+comp) as tarf:
                for path in paths:
                    self._copy_data(container, tarf, path)
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

    def _write_control(self, job, tarf):
        control_data = self.value.get('control', {})
        if 'Package' not in control_data:
            raise RuntimeError('Missing control package name')
        if 'Version' not in control_data:
            raise RuntimeError('Missing control version')
        if 'Architecture' not in control_data:
            raise RuntimeError('Missing control architecture')

        fields = sorted(control_data.keys(), key=self._control_sort_key)
        control = io.BytesIO()
        for field in fields:
            val = job.template(control_data[field])
            control.write(field.encode('utf-8'))
            control.write(b": ")
            if "\n" in val:
                lines = val.split("\n")
                while lines[-1] == "":
                    del lines[-1]

                for num, line in enumerate(lines):
                    if num != 0:
                        control.write(b" ")
                    control.write(line.encode('utf-8'))
                    control.write(b"\n")
            else:
                control.write(val.encode('utf-8'))
                control.write(b"\n")
        control.seek(0)

        info = tarfile.TarInfo("control")
        info.size = len(control.getvalue())
        tarf.addfile(info, control)

    def _copy_data(self, container, tarf, path):
        dirname = os.path.join(".", os.path.relpath(os.path.dirname(path), "/"))
        tstream, tstat = container.get_archive(path)
        tf = IOFromIterable(tstream)

        with tarfile.open(fileobj=tf, mode="r|") as tin:
            while True:
                ti = tin.next()
                if ti is None:
                    break
                tdata = tin.extractfile(ti) if ti.isreg() else None

                ti.name = os.path.join(dirname, ti.name)

                tarf.addfile(ti, tdata)
