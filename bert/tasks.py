
import io
import os
import posixpath
import re
import tarfile
import tempfile

from .utils import file_hash, IOFromIterable

TASKS = {}

def get_task(name, value):
    cls = TASKS[name]
    return cls(value)

#
#
#

class Task(object):
    task_name = None

    def __init_subclass__(cls, name, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.task_name = name
        TASKS[name] = cls

    def __init__(self, value):
        self.value = value
        self.setup()

    def setup(self):
        pass

    def run(self, job):
        raise NotImplementedError

#
#
#

class TaskAdd(Task, name="add"):
    def run(self, job):
        container = job.create({
            'value' : self.value,
            'file_sha256' : file_hash('sha256', self.value)
        })

        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                tar.add(self.value)

            container.put_archive(
                path=job.work_dir,
                data=tf
            )

        job.commit()

class TaskExportBin(Task, name="export-bin"):
    def run(self, job):
        container = job.create({})

        install_path = self.value['install-path']
        name = os.path.join(job.dist_dir, job.template(self.value["name"]))
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

        os.makedirs(job.dist_dir, exist_ok=True)
        with open(name, "wb") as f:
            f.write(header_data)

            with tarfile.open(fileobj=tf, mode="r:") as tin, tarfile.open(fileobj=f, mode="w:bz2") as tout:
                while True:
                    ti = tin.next()
                    if ti is None:
                        break
                    tout.addfile(ti, tin.extractfile(ti))

        os.chmod(name, 0o775)

class TaskRun(Task, name="run"):
    def run(self, job):
        if self.value.startswith("./"):
            command = posixpath.join(job.work_dir, self.value)

            container = job.create({
                'value' : self.value,
                'file_sha256' : file_hash('sha256', self.value)
            }, command=command)

            with tempfile.TemporaryFile() as tf:
                with tarfile.open(fileobj=tf, mode="w") as tar:
                    tar.add(self.value)
                tf.seek(0)

                container.put_archive(
                    path=job.work_dir,
                    data=tf
                )
        else:
            container = job.create({
                'value' : self.value
            }, command=self.value)

        job.commit()

class TaskReadFile(Task, name="read-file"):
    def run(self, job):
        container = job.create({})

        with tempfile.TemporaryFile() as tf:
            tstream, tstat = container.get_archive(self.value['path'])
            for chunk in tstream:
                tf.write(chunk)
            tf.seek(0)

            with tarfile.open(fileobj=tf, mode="r") as tar:
                for item in tar.members:
                    data = tar.extractfile(item).read().decode('utf-8')
                    if data.endswith("\n"):
                        data = data[:-1]
                    job.vars[self.value['var']] = data
                    break

        job.cancel()

class TaskSetup(Task, name="setup"):
    def run(self, job):
        container = job.create({})

        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                info = tarfile.TarInfo(job.work_dir)
                info.type = tarfile.DIRTYPE
                tar.addfile(info, io.BytesIO())
            tf.seek(0)

            container.put_archive(
                path="/",
                data=tf
            )

        job.commit()
