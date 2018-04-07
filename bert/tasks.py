
import io
import os
import posixpath
import tarfile
import tempfile

from .utils import file_hash

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

class TaskAdd(Task, name="setup"):
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
