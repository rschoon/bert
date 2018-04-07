
import click
import docker
import dockerpty
import yaml

from .tasks import get_task
from .utils import json_hash

LABEL_BUILD_ID = "bert.build_id"

class BuildImageExists(Exception):
    def __init__(self, image):
        self.image = image

class BuildFailed(Exception):
    def __init__(self, rc=0):
        self.rc = rc

    def __repr__(self):
        return "BuildFailed(rc={0.rc})".format(self)

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

class BertTask(object):
    def __init__(self, taskinfo):
        self.name = taskinfo.pop("name", None)

        action, value = taskinfo.popitem()
        assert not taskinfo
        self._task = get_task(action, value)

    @property
    def task_name(self):
        return self._task.task_name

    @property
    def key_params(self):
        # Don't peak into child task, it is expected to provide details to .create()
        return {}

    @property
    def display_name(self):
        if self.name:
            return self.name
        return "%s: %s"%(self.task_name, self._task.value)

    def run(self, job):
        try:
            return self._task.run(job)
        except BuildImageExists as bie:
            job._commit_from_image(bie.image)

class BuildJob(object):
    def __init__(self, image):
        # XXX timeout is problematic
        self.docker_client = docker.from_env(timeout=300)

        self.work_dir = "/var/tmp"
        self.src_image = image
        self.current_key_id = None
        self.current_task = None
        self.current_container = None
        self._all_containers = []

    def setup(self):
        click.echo(">>> Pulling: {}".format(self.src_image))
        self.docker_client.images.pull(self.src_image)

    def create(self, job_key, command=None):
        ct = self.current_task
        self.current_key_id = json_hash('sha256', [
            self.src_image,
            ct.task_name,
            ct.key_params,
            job_key
        ])

        click.echo(">>> Build: {}".format(self.current_task.display_name))
        click.echo("--- Id: {}".format(self.current_key_id))

        images = self.docker_client.images.list(filters={
            'label' : '{}={}'.format(LABEL_BUILD_ID, self.current_key_id)
        }, all=True)
        if images:
            raise BuildImageExists(images[0])

        self.current_container = self.docker_client.containers.create(
            image=self.src_image,
            labels={LABEL_BUILD_ID : self.current_key_id},
            command=command,
            stdin_open=True,
            tty=True
        )
        return self.current_container

    def commit(self):
        assert self.current_container

        try:
            dockerpty.start(self.docker_client.api, self.current_container.id)
        except KeyboardInterrupt:
            pass

        # If we were interrupted, we got here early and need to stop.
        # If not, we are stopped anyway.
        self.current_container.stop()

        # Determined if we were successful.
        result = self.current_container.wait()
        if result['StatusCode'] != 0:
            raise BuildFailed(rc=result['StatusCode'])

        image = self.current_container.commit(
            changes="LABEL {}={}".format(LABEL_BUILD_ID, self.current_key_id)
        )

        self.src_image = image.id
        self.current_container = None

        click.echo("--- New Image: {}".format(self.src_image))
        self.cleanup()

    def _commit_from_image(self, image):
        self.src_image = image.id
        click.echo("--- Existing Image: {}".format(self.src_image))

    def cleanup(self):
        for container in self._all_containers[::-1]:
            if container == self.current_container:
                continue
            self.docker_client.remove_container(container)
            self._all_containers.remove(container)

    def close(self):
        self.current_container = None
        self.cleanup()

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
        job = BuildJob(img)

        try:
            job.setup()
            for task in self.tasks:
                job.current_task = task
                task.run(job)
        finally:
            job.close()
