
import io
import os
import posixpath
import tarfile
import tempfile

from . import Task
from ..utils import file_hash, value_hash

class TaskScript(Task, name="script"):
    def run(self, job):
        script = contents = None
        if isinstance(self.value, dict):
            contents = self.value.get("script") or self.value.get("contents")
            if contents is None:
                script = [self.value.get("path")]
            else:
                contents = job.template(contents)
        elif isinstance(self.value, list):
            script = self.value
        else:
            script = [self.value]

        if contents is not None:
            contents_bytes = contents.encode('utf-8')
            content_hash = value_hash('sha256', contents_bytes)
            script_name = "script-"+content_hash
            command = ["./"+script_name]

            script_info = tarfile.TarInfo(name=script_name)
            script_info.mode = 0o755
            script_info.size = len(contents_bytes)

            self._run(job, {
                'value' : command,
                'file_sha256' : content_hash
            }, command, script_info, io.BytesIO(contents_bytes))
        else:
            script = [job.template(a) for a in script]
            command = [posixpath.join(job.work_dir, script[0])]+script[1:]

            script_info = tarfile.TarInfo(name=script[0])
            script_info.mode = 0o755
            script_info.size = os.path.getsize(script[0])

            with open(script[0], "rb") as script_fileobj:
                self._run(job, {
                    'value' : script[0] if len(script) == 1 else script,
                    'file_sha256' : file_hash('sha256', script[0])
                }, command, script_info, script_fileobj)

    def _run(self, job, job_json, command, script_info, script_fileobj):
        container = job.create(job_json, command=command)
        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                tar.addfile(script_info, fileobj=script_fileobj)
            tf.seek(0)

            container.put_archive(
                path=job.work_dir,
                data=tf
            )

        job.commit()
