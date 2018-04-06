
import io
import subprocess
import tarfile
import tempfile

import yaml

from .tasks import get_task

def expect_type(val, type_):
    if type_ is None:
        return val
    return type_(val)

def expect_list(val, subtype=None):
    if isinstance(val, list):
        return [expect_type(v, subtype) for v in val]
    if subtype is not None and isinstance(val, subtype):
        return [val]
    raise ValueError("Invalid value type")

def tar_add_string(tar, name, s):
    data = s.encode('utf-8')
    df = io.BytesIO(data)
    df.seek(0)

    info = tarfile.TarInfo("Dockerfile")
    info.size = len(data)

    tar.addfile(info, df)

class BertTask(object):
    def __init__(self, taskinfo):
        self.name = taskinfo.pop("name", None)

        action, value = taskinfo.popitem()
        assert not taskinfo
        self._task = get_task(action, value)

    def render_dockerfile(self, *args, **kwargs):
        return self._task.render_dockerfile(*args, **kwargs)

class BertDockerFile(object):
    def __init__(self):
        self._lines = []
        self._files = []
        self.work_dir = "/var/tmp"

    def add_file(self, fn):
        self._files.append(fn)

    def append(self, line):
        self._lines.append(line)

class BertBuild(object):
    def __init__(self, filename):
        self.filename = filename

        self.build_tag = None
        self.from_ = None
        self.tasks = []

        self._parse()

    def __repr__(self):
        return "BertBuild(%r)"%(self.filename, )

    def _parse(self):
        with open(self.filename, "r") as f:
            data = yaml.safe_load(f)

            self.build_tag = data.pop("build-tag", None)
            self.from_ = expect_list(data.pop("from"), str)
            self.tasks = list(self._iter_parse_tasks(data.pop("tasks")))

    def _iter_parse_tasks(self, tasks):
        tasks = expect_list(tasks, dict)
        for task in tasks:
            yield BertTask(task)

    def build(self):
        for from_image in self.from_:
            self._build_from(from_image)

    def _build_from(self, img):
        df = BertDockerFile()
        df.append("FROM {}".format(img))
        df.append("WORKDIR {}".format(df.work_dir))

        for task in self.tasks:
            task.render_dockerfile(df)

        with tempfile.NamedTemporaryFile() as tf:
            print("\n".join(df._lines))
            with tarfile.open(tf.name, "w") as tar:
                tar_add_string(tar, "DockerFile", "\n".join(df._lines))
                for fn in df._files:
                    tar.add(fn)
            tf.seek(0)

            cmd = ["docker", "build"]
            if self.build_tag is not None:
                cmd.extend(["-t", self.build_tag])
            cmd.append("-")

            try:
                subprocess.check_call(cmd, stdin=tf)
            except subprocess.CalledProcessError as exc:
               raise RuntimeError("%r failed: %d"%(exc.cmd, exc.returncode))
