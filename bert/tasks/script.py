
import io
import os
import shlex
import tarfile
import tempfile

from . import Task, TaskVar
from ..utils import file_hash, value_hash

class TaskScript(Task, name="script"):
    """
    Run a script on the container image.
    """

    class Schema:
        script = TaskVar(bare=True, help="Script to push to container and run")
        contents = TaskVar(help="Script contents to push to container and run")

    def run_with_values(self, job, *, script, contents):
        if isinstance(script, str):
            script = shlex.split(script)
        if not script and not contents:
            raise ValueError("Either script or contents is required")

        script_name = "/.bert-build.script"

        if contents is not None:
            contents_bytes = contents.encode('utf-8')
            content_hash = value_hash('sha256', contents_bytes)

            script_info = tarfile.TarInfo(name=script_name)
            script_info.mode = 0o755
            script_info.size = len(contents_bytes)

            self._run(job, {
                'value': [],
                'file_sha256': content_hash
            }, script_info, io.BytesIO(contents_bytes), script_name, [])
        else:
            script_info = tarfile.TarInfo(name=script_name)
            script_info.mode = 0o755
            script_info.size = os.path.getsize(script[0])

            with open(script[0], "rb") as script_fileobj:
                self._run(job, {
                    'value': script[0] if len(script) == 1 else script,
                    'file_sha256': file_hash('sha256', script[0])
                }, script_info, script_fileobj, script_name, script[1:])

    def _run(self, job, job_json, script_info, script_fileobj, script_name, args):
        # TODO XXX Remove the script after it runs.  Unfortunately we
        # don't want to assume rm exists, so this is more difficult
        # (push a script wrapper binary perhaps?)
        container = job.create(job_json, command=[script_name] + args)
        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                tar.addfile(script_info, fileobj=script_fileobj)
            tf.seek(0)

            container.put_archive(
                path="/",
                data=tf
            )

        job.commit()
