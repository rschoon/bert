
import os
import re
import tarfile

from . import Task
from ..utils import IOFromIterable

class TaskExportBin(Task, name="export-bin"):
    def run(self, job):
        container = job.create({})

        install_path = self.value['install-path']
        try:
            dest = job.template(self.value["dest"])
        except KeyError:
            dest = job.template(self.value["name"])
        msg = job.template(self.value["msg"])

        tstream, tstat = container.get_archive(install_path)
        tf = IOFromIterable(tstream)

        header = """#!/bin/sh -e
        rm -rf {}
        echo '{}'
        sed -e '1,/^exit$/d' "$0" | tar -xjf - -C {}
        exit
        """.format(install_path, msg, os.path.dirname(install_path))
        header_data = ("\n".join(re.split(r"\n\s+", header))).encode('utf-8')

        with open(name, "wb") as f:
            f.write(header_data)

            with tarfile.open(fileobj=tf, mode="r|") as tin, tarfile.open(fileobj=f, mode="w:bz2") as tout:
                while True:
                    ti = tin.next()
                    if ti is None:
                        break
                    tout.addfile(ti, tin.extractfile(ti) if ti.isreg() else None)

        os.chmod(name, 0o775)
