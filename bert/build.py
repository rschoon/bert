
from collections import OrderedDict
import click
import docker
import dockerpty
from jinja2 import Template
import yaml

from .tasks import get_task
from .utils import json_hash

LABEL_BUILD_ID = "bert.build_id"

class BuildImageExists(Exception):
    def __init__(self, image):
        self.image = image

class BuildFailed(Exception):
    def __init__(self, msg=None, rc=0):
        self.msg = msg
        self.rc = rc

    def __repr__(self):
        return "BuildFailed(msg={0.msg:r}, rc={0.rc})".format(self)

#
#
#

class YamlLoader(yaml.SafeLoader):
    pass

def _construct_yaml_mapping(loader, node):
    loader.flatten_mapping(node)
    return OrderedDict(loader.construct_pairs(node))

YamlLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                           _construct_yaml_mapping)

#
#
#

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

#
#
#

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
        if self._task.value is not None:
            return "%s: %s"%(self.task_name, self._task.value)
        return self.task_name

    def run(self, job):
        try:
            return self._task.run(job)
        except BuildImageExists as bie:
            job._commit_from_image(bie.image)

class CurrentTask(object):
    def __init__(self, task):
        self.image = None
        self.key_id = None
        self.task = task
        self.container = None
        self.command = None
        self.image = None

    @property
    def display_name(self):
        return self.task.display_name

class BuildJob(object):
    def __init__(self, image):
        # XXX timeout is problematic
        self.docker_client = docker.from_env(timeout=600)

        self.changes = []
        self.work_dir = "/bert-build"
        self.cache_dir = "cache"
        self.src_image = image
        self.current_task = None
        self._all_containers = []
        self.vars = {}

    def setup(self):
        click.echo(">>> Pulling: {}".format(self.src_image))
        self.docker_client.images.pull(self.src_image)

        self.run_task(BertTask({"setup" : None}))

    def run_task(self, task):
        self.current_task = CurrentTask(task)
        task.run(self)

    def create(self, job_key, command=None):
        if self.current_task is None:
            raise BuildFailed("Task Create: No current task")

        ct = self.current_task.task
        key_id = self.current_task.key_id = json_hash('sha256', [
            self.src_image,
            ct.task_name,
            ct.key_params,
            job_key
        ])

        click.echo(">>> Build: {}".format(self.current_task.display_name))
        click.echo("--- Id: {}".format(key_id))

        images = self.docker_client.images.list(filters={
            'label' : '{}={}'.format(LABEL_BUILD_ID, key_id)
        }, all=True)
        if images:
            raise BuildImageExists(images[0])

        image = self.src_image
        if isinstance(image, str):
            image = self.docker_client.images.get(self.src_image)
        self.current_task.image = image

        self.current_task.command = command
        container = self.current_task.container = self.docker_client.containers.create(
            image=self.src_image,
            labels={LABEL_BUILD_ID : key_id},
            command=command,
            working_dir=self.work_dir,
            stdin_open=True,
            tty=True
        )
        return container

    def commit(self):
        if self.current_task is None:
            raise BuildFailed("Task Commit: No current task")

        container = self.current_task.container
        if container is None:
            raise BuildFailed("Task Commit: No current container to commit")

        if self.current_task.command is not None:
            try:
                dockerpty.start(self.docker_client.api, container.id)
            except KeyboardInterrupt:
                pass

            # If we were interrupted, we got here early and need to stop.
            # If not, we are stopped anyway.
            container.stop()

            # Determined if we were successful.
            result = container.wait()
            if result['StatusCode'] != 0:
                raise BuildFailed(rc=result['StatusCode'])

        changes = [
            "LABEL {}={}".format(LABEL_BUILD_ID, self.current_task.key_id) 
        ]
        if self.current_task.image is not None:
            cmd = self.current_task.image.attrs.get("Cmd")
            if self.current_task.command and cmd:
                changes.append("CMD {}".format(json.dumps(cmd)))

        # This can take a while...
        image = container.commit(
            changes="\n".join(changes)
        )

        self.changes.append(image.id)
        self.src_image = image.id
        self.current_task = None

        click.echo("--- New Image: {}".format(self.src_image))
        self.cleanup()

    def cancel(self):
        self.current_container = None
        self.current_command = None
        self.cleanup()

    def _commit_from_image(self, image):
        self.src_image = image.id
        click.echo("--- Existing Image: {}".format(self.src_image))

    def template(self, txt):
        if txt is None:
            return txt
        tpl = Template(txt)
        return tpl.render(**self.vars)

    def cleanup(self):
        current_container = None
        if self.current_task is not None:
            current_container = self.current_task.container

        for container in self._all_containers[::-1]:
            if container == current_container:
                continue
            self.docker_client.remove_container(container)
            self._all_containers.remove(container)

    def close(self):
        self.current_container = None
        self.cleanup()

class BertStage(object):
    def __init__(self, config, name=None, defaults={}):
        self.name = name
        self.build_tag = config.pop("build-tag", None)
        try:
            self.from_ = expect_list(config.pop("from"), str)
        except KeyError:
            self.from_ = defaults['from']
        self.tasks = list(self._iter_parse_tasks(config.pop("tasks")))

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
                job.run_task(task)

            if self.build_tag:
                img = job.docker_client.images.get(job.src_image)
                img.tag(self.build_tag)
        finally:
            job.close()

class BertBuild(object):
    def __init__(self, filename):
        self.filename = filename
        self.stages = []
        self.stage_defaults = {}
        self._parse()

    def __repr__(self):
        return "BertBuild(%r)"%(self.filename, )

    def _parse(self):
        with open(self.filename, "r") as f:
            config = yaml.load(f, YamlLoader)

            if 'tasks' in config:
                self.stages.append(BertStage(config))
            else:
                for name in ('from', ):
                    try:
                        self.stage_defaults[name] = config.pop(name)
                    except KeyError:
                        pass

                stages = config.pop("stages")
                for stage_name, stage in stages.items():
                    stage = BertStage(stage, name=stage_name,
                                      defaults=self.stage_defaults)
                    self.stages.append(stage)

    def build(self):
        for stage in self.stages:
            stage.build()
