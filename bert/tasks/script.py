
import io
import os
import shlex
import tarfile
import tempfile

from . import Task, TaskVar
from ..utils import file_hash, value_hash, LocalPath

class TaskScript(Task, name="script"):
    """
    Run a script on the container image.
    """

    class Schema:
        script = TaskVar(bare=True, help="Script to push to container and run", type=LocalPath)
        contents = TaskVar(help="Script contents to push to container and run")
        template = TaskVar(help="Treat script file via `script` as a template", default=False, type=bool)

    def run_with_values(self, job, *, script, contents, template):
        if hasattr(script, "__fspath__"):
            script = script.__fspath__()
        if isinstance(script, str):
            script = shlex.split(script)
        if not script and not contents and not template:
            raise ValueError("Either script or contents is required")

        script_name = "/.bert-build.script"
        script_args = []
        if script:
            script_args = script[1:]

        if template:
            with open(script[0], "r", encoding="utf-8") as script_fileobj:
                contents = job.template(script_fileobj.read())

        if contents is not None:
            contents_bytes = contents.encode('utf-8')
            content_hash = value_hash('sha256', contents_bytes)

            script_info = tarfile.TarInfo(name=script_name)
            script_info.mode = 0o755
            script_info.size = len(contents_bytes)

            self._run(job, self._job_key(
                value=[],
                file_sha256=content_hash,
                template=template
            ), script_info, io.BytesIO(contents_bytes), script_name, script_args)
        else:
            script_info = tarfile.TarInfo(name=script_name)
            script_info.mode = 0o755
            script_info.size = os.path.getsize(script[0])

            with open(script[0], "rb") as script_fileobj:
                self._run(job, self._job_key(
                    value=script[0] if len(script) == 1 else script,
                    file_sha256=file_hash('sha256', script[0]),
                    template=template
                ), script_info, script_fileobj, script_name, script_args)

    def _job_key(self, *, value, file_sha256, template):
        jk = {
            'value': value,
            'file_sha256': file_sha256,
        }
        if template:
            jk['template'] = True
        return jk

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
